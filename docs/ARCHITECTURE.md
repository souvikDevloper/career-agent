# Architecture

How Career Agent is put together, and — more importantly — **where each guarantee is
enforced**. The product's claims ("no invented qualifications", "the model can't bypass
your rules", "never a silent double-apply") are only worth something if they live in
code paths that a prompt cannot talk its way around. This document points at those paths.

- [Shape of the system](#shape-of-the-system)
- [The two request paths](#the-two-request-paths)
- [Application state machine](#application-state-machine)
- [Authorization: Cedar and the gate](#authorization-cedar-and-the-gate)
- [The submission gate protocol](#the-submission-gate-protocol)
- [Data model](#data-model)
- [Transactional outbox](#transactional-outbox)
- [Truthfulness: where "no invented facts" is enforced](#truthfulness-where-no-invented-facts-is-enforced)
- [Scheduled work](#scheduled-work)
- [Failure handling](#failure-handling)
- [Cost and operations](#cost-and-operations)

---

## Shape of the system

Everything is serverless and event-driven. There is no NAT gateway, no load balancer and
no always-on compute.

```
                    ┌─────────────────────── CloudFront ───────────────────────┐
                    │  S3 (React UI)            /api/* → HTTP API (same origin) │
                    └──────────────────────────────┬───────────────────────────┘
                                                   │  Cognito JWT
                                                   ▼
  mic ──► Transcribe (presigned,           ┌──────────────┐
          streaming)                       │ ApiFunction  │───────────────┐
                                           └──────┬───────┘               │
                                                  │ writes                │ Invoke
                                                  ▼                       │ (sync)
                                    ┌─────────────────────────┐           │
                                    │ DynamoDB (single table) │           │
                                    │  + transactional outbox │           │
                                    └───────────┬─────────────┘           │
                                                │ Streams (NEW_IMAGE)     │
                                                ▼                         │
                                         ┌──────────────┐                 │
                                         │RelayFunction │                 │
                                         └──┬────┬──────┘                 │
                        ┌───────────────────┘    └────────────┐           │
                        ▼                                     ▼           │
                  SQS work                            SQS notify          │
                        │                                     │           │
                        ▼                                     ▼           │
               ┌─────────────────┐                   ┌────────────────┐   │
               │ WorkerFunction  │                   │NotifierFunction│   │
               │ Strands + Nova  │                   │  SES, Telegram │   │
               └────────┬────────┘                   └────────────────┘   │
                        │ outbox → SQS submit (FIFO, group = user)         │
                        ▼                                                  │
               ┌─────────────────┐        Invoke         ┌──────────────┐  │
               │ BrowserFunction │◄─────────────────────►│ GateFunction │◄─┘
               │ Node 22 +       │   begin / dispatch /  │ Cedar, quota,│
               │ Playwright      │       complete        │ fencing      │
               └────────┬────────┘                       └──────────────┘
                        │ fills & submits
                        ▼
               PortalFunction (fictional test employer) ──HMAC webhook──► ApiFunction

  EventBridge Scheduler ──► ScheduledFunction   (monitor every 5 min, cleanup every 6 h)
```

**Lambda functions** (`template.yaml`): `ApiFunction`, `WorkerFunction`, `RelayFunction`,
`ScheduledFunction`, `NotifierFunction`, `GateFunction`, `PortalFunction`, `BrowserFunction`.

**Queues**, each with its own dead-letter queue and SSE enabled:

| Queue | Type | Carries |
|---|---|---|
| `WorkQueue` | standard, 3 receives | agent work: prepare, reconcile, classify |
| `SubmitQueue` | **FIFO**, 5 receives | one submission at a time **per user** (`MessageGroupId` = user) |
| `NotifyQueue` | standard, 4 receives | dashboard / SES / Telegram fan-out |

The FIFO grouping is load-bearing: it is what stops two submissions for the same user
racing each other into the same employer form.

---

## The front door

CloudFront is the intended entry point and does five jobs: terminates TLS, serves the SPA
from a **private** S3 bucket via Origin Access Control, routes `/api/*` and `/portal*` to
API Gateway so the browser sees **one origin**, rewrites extensionless paths to
`index.html` for client-side routes, and sets the security headers — including the
`Permissions-Policy` that grants microphone access.

A new AWS account cannot create a distribution until activation completes:
`CreateDistribution` returns 403 no matter what IAM permits, and the stack rolls back at
that single resource while every other CloudFront resource creates normally. The
`UseCloudFront` parameter therefore has a second mode. With it `false`, a `WebFunction`
behind the HTTP API's `$default` route serves the same built assets out of the same private
bucket over IAM — same origin, same TLS, same SPA rewrite, same headers. The only thing
given up is edge caching: every asset request reaches Lambda. Content-hashed assets are
still served `immutable` and the shell `no-cache`, so it costs latency, not correctness.

Either way the app's own code is identical — it only ever calls same-origin relative paths.

---

## The two request paths

**Synchronous** — anything the person is waiting on. `CloudFront → HTTP API → ApiFunction`,
authorized by a Cognito JWT. The API writes to DynamoDB and returns; it never calls the
model or the browser inline.

**Asynchronous** — everything slow or risky. The API commits a state change *and* an outbox
row in one transaction; the relay turns that row into an SQS message; a worker picks it up.
The person's request never blocks on Bedrock, Playwright or an employer's site.

This split is why a timeout in a browser worker can never lose a state change: the state
change was already committed before the work was dispatched.

---

## The agent's tools, and the second front door

The agent has a registry of allowlisted, typed business tools (`agent.TOOLS`). They are
plain functions: no shell, no arbitrary fetch, no credential access, no policy editing.
Each one re-derives the owner from the verified session rather than taking a user id, and
authorization is enforced by backend code and Cedar, never by the prompt.

That registry is served two ways. The voice and chat agent calls it through Strands (or a
Bedrock Converse tool loop when Strands is unavailable). An **MCP** server at `POST
/api/mcp` serves the same registry to any Model Context Protocol client, so a judge can
add the connector in their own client and drive the real system.

`describe_tool()` builds the schema for both. The Bedrock `toolSpec` and the MCP
`inputSchema` come from one function reading one set of docstrings, including the `Args:`
block, which becomes per-parameter documentation. A tool therefore cannot be described one
way to the voice agent and another way to a connector, and the Connectors page in the app
proves it by running a real handshake against the live endpoint instead of describing one.

Three properties matter more than the protocol plumbing:

- **Identity.** `/api/mcp` sits under the existing `ANY /api/{proxy+}` route, so API
  Gateway's JWT authorizer runs before any of this code does. The owner comes from the
  validated token; no tool accepts a user id, so a body that names one is rejected outright.
- **Approval is not on this surface.** Submitting is the one irreversible act in the
  product, and the guard on it is that a person asked in their own words — which a tool call
  arriving from another model cannot evidence. `prepare_application` is served; approving
  stays in the app. Calling it anyway returns an `isError` result saying where to go, and
  the function never runs.
- **Tool failures are results, not protocol errors.** A JSON-RPC error aborts the caller's
  turn; an `isError` result lets its model read what went wrong and try something else.

Reads do not write an operation record — only `search_jobs` needs one to stream progress
into, and a DynamoDB write nobody reads still costs money.

---

## Application state machine

Defined in `backend/src/career_agent/workflow.py` as `STATES` and `TRANSITIONS`, and
enforced on every write — an illegal transition raises rather than being persisted.

```
Discovered ──► Ineligible ──► Preparing
     │                           │
     └──────────► Preparing ◄────┘
                     │
      ┌──────────────┼───────────────┬──────────────────┐
      ▼              ▼               ▼                  ▼
NeedsInformation  NeedsApproval  Authorized      ManualHandoff
      │              │               │                  │
      └──► Preparing └──► Authorized │                  └──► Submitted
                                     ▼
                                  Queued ──► Paused ──► Queued
                                     │
                                     ▼
                                Submitting
                                     │
              ┌──────────────────────┼────────────────────────┐
              ▼                      ▼                        ▼
          Submitted            KnownFailure            OutcomeUnknown
                                     │                        │
                                     ▼                        ▼
                                 Preparing            Submitted │ NeedsReview
```

`Submitted` and `Withdrawn` are terminal (`TRANSITIONS` maps both to the empty set).
`Submitting` and `OutcomeUnknown` deliberately have **no** path to `Withdrawn` either — once
a form may already have been submitted, the record has to be resolved, not quietly dropped.
Every other state can be withdrawn.

The transition helper is also the optimistic-concurrency point: each update is conditional
on both the row's `version` and its current `action_state`, so two concurrent writers cannot
both advance the same application.

The state worth dwelling on is **`OutcomeUnknown`**. When a browser worker times out after
clicking Submit, the honest answer is "we do not know whether that landed". The system
does not guess. It moves to `OutcomeUnknown`, keeps consuming the user's daily capacity,
and schedules reconciliation — which resolves to `Submitted` if a receipt is found or
`NeedsReview` if it cannot be determined. There is no path from `OutcomeUnknown` back to
a state that would let a second submission happen automatically.

Separately from `action_state` (what the agent did), each application carries a
`recruitment_stage` (what the *employer* did): `applied`, `reply_received`,
`assessment_invited`, `interview_scheduled`, `offer`, `rejected`, `withdrawn`. The two are
tracked independently so an employer's silence is never confused with an agent failure.

---

## Authorization: Cedar and the gate

`policies/career_agent.cedar` defines seven actions:

```
view_application   prepare_application   approve_application   submit_application
cancel_application   publish_profile   send_referral
```

Cedar is evaluated by `cedarpy` inside `backend/src/career_agent/policy.py`. Two properties
matter:

1. **The model never evaluates policy.** The agent loop can *request* a submission; it
   cannot authorize one. Authorization is a separate call against live DynamoDB facts.
2. **Decisions are computed fresh at the moment of submission**, not cached from when the
   packet was prepared. A mandate revoked thirty seconds ago is honoured.

The three approval modes (`review`, `auto_above_80`, `auto_eligible`) are settings that
feed the Cedar context — they are not branches in prompt text. `auto_above_80` is strictly
greater than 80, and the boundary is unit-tested at 80/81.

Cedar decisions are the *policy* half. The *concurrency* half — daily caps, cooldowns,
one-submission-at-a-time — is enforced by DynamoDB conditional writes and transactions,
because a policy engine cannot make a race condition impossible. Both must pass.

---

## The submission gate protocol

`BrowserFunction` runs Playwright and Chromium. It holds **no business rules and no
DynamoDB permissions**. Everything it is allowed to do is decided by `GateFunction`, which
it calls synchronously (`handlers/gate.py`). Three operations:

**`begin`** — the worker asks permission to start.
The gate re-checks Cedar, reserves daily capacity atomically, takes a lease, and computes a
**fencing token** (`fencing = app.version + 1`). It returns either `proceed` (with the
target URL, the answers, a 300-second presigned resume URL and the field list), or
`reconcile`, or a refusal with the reason. The worker receives only what it needs for this
one form — never the user's profile.

**`dispatch`** — the worker has loaded the form and is about to click Submit.
It sends the live form's HTML; the gate parses it and compares the **form signature**
against the one the packet was built from. If the employer changed the form, the answers no
longer map to the fields they were verified against, and the gate refuses. The write is
conditional on `fencing` still matching **and** `dispatched_at` not existing:

```python
condition=And(C("fencing", "eq", fencing), C("dispatched_at", "not_exists"), ...)
```

That condition is the no-double-apply guarantee. Once an attempt is marked dispatched, no
worker — including a retried copy of the same worker, or a replacement after a timeout —
can ever mark it dispatched again. A stale worker whose lease expired carries an old
fencing token and fails the condition.

**`complete`** — the worker reports the outcome, with the employer's reference and an
evidence screenshot written to S3 under `evidence/{uid}/{app_id}/{attempt_id}`.

---

## Data model

A single DynamoDB table, `PAY_PER_REQUEST`, with `pk`/`sk`, one GSI (`gsi1pk`/`gsi1sk`),
`StreamViewType: NEW_IMAGE`, and TTL on `ttl`.

All of a user's items share `pk = USER#{user_id}`, so a user's data is one query and
isolation is a partition-key property rather than a filter someone can forget:

| `sk` | Item |
|---|---|
| `APP#{app_id}` | application: state, score, packet hash, fencing, current attempt |
| `PACKET#{app_id}#{version:04d}` | immutable packet version — answers, field evidence, form signature |
| `ATTEMPT#{app_id}#{attempt_id}` | one submission attempt: lease, dispatch, outcome, Cedar decision |
| `PROFILE#CURRENT` → `PROFILE#V#{version:06d}` | pointer + immutable profile versions |
| `MATCH#{job_key}` | score, components, filters, evidence, rubric version |
| `JOB#…`, `SOURCE#{source}`, `WATCH#{watch_id}` | discovery inputs and schedules |
| `LEDGER#{local_date}` | the day's submission count, in the user's timezone |
| `EVENT#{ts}#{event_id}` | the timeline the UI reads |
| `TASK#{task_id}`, `MSG#{message_id}` | deadlines and employer messages |

Outbox rows live at `pk = OUTBOX#{id}`, with `OUTBOX#pending` on the GSI so the repair
sweep can find anything the stream dropped.

Two details that carry weight:

- **Packets are immutable and versioned.** An approval is bound to a specific
  `packet_hash`. Change anything in the packet and the hash changes, which invalidates the
  approval and sends it back for a fresh one. You cannot approve one thing and have another
  submitted.
- **The daily ledger is keyed by the user's local date**, not UTC, so "5 per day" means
  what the user thinks it means.

`backend/src/career_agent/store.py` abstracts this behind a `Store` interface with a small
declarative condition DSL (`C`, `And`, `Or`). `DynamoStore` runs in AWS; `MemoryStore`
implements *identical* conditional semantics, which is what makes the race-condition tests
(cap races, revoked mandates, stale fencing) runnable in unit tests with no AWS.

---

## Transactional outbox

The failure this avoids: write the state change, then fail before enqueuing the work — or
enqueue the work, then fail before the state change. Either way the system lies.

Instead, `Workflow.outbox_put()` returns a `Put` that is committed **in the same DynamoDB
transaction** as the state change. Then:

1. DynamoDB Streams (`NEW_IMAGE`) deliver the new row to `RelayFunction`.
2. The relay sends it to the queue named on the row (`work`, `submit`, `notify`), using the
   row's dedupe key as `MessageDeduplicationId` and its group as `MessageGroupId` for FIFO.
3. The row is marked `dispatched` conditionally, so a replayed stream record is a no-op.
4. The 5-minute monitor re-sends anything still `pending`, covering the case where the
   stream itself dropped a record.

So a message is sent *at least* once and acted on *at most* once — the state change and its
side effect can never disagree.

---

## Truthfulness: where "no invented facts" is enforced

This is the part that is easiest to claim and hardest to actually do, so it is worth being
precise about the mechanism.

**Evidence is verified against the source text, not trusted from the model.**
`resume.py` asks Nova for facts *with an exact supporting quote*, then
`verify_facts(facts, text)` marks each fact `verified` **only if that quote is actually
found in the resume text**. A fabricated quote fails the check. The model's output is
treated as a claim to be checked, not an answer.

**Some fields are never inferred at all.** Work authorization is hard-coded to
`{"value": None, "verified": False}` after extraction — no resume wording can set it. It
comes from the user or it becomes a question. Demographic fields are answered from policy
(`decline_to_self_identify`), never generated.

**Every packet field is traceable.** Each answer carries its provenance —
`resume:education`, `profile:user_confirmed`, `saved_answer:user_consent`,
`generated:grounded_note`, `policy:decline_to_self_identify` — and the UI shows it next to
the value. A required field with no verified source does not get a plausible guess; it
becomes `NeedsInformation` and the application stops.

**Scores are a stated rubric, not a vibe.** `scoring.py` pins `RUBRIC_VERSION =
"fit-rubric/1.0"`; eligibility filters are deterministic; the model only supplies evidence
that is then verified. Every stored match records the rubric version that produced it, so
an old score is never silently re-interpreted under new rules.

---

## Scheduled work

Two EventBridge Scheduler rules target `ScheduledFunction`:

| Schedule | Rate | Does |
|---|---|---|
| `MonitorSchedule` | 5 minutes | poll job sources, send due reminders, repair the outbox |
| `CleanupSchedule` | 6 hours | delete expired example workspaces |

Source polling compares a content hash before doing anything: an unchanged feed costs zero
model calls. This is what makes "watches while you sleep" affordable rather than a way to
burn a credit balance overnight.

---

## Failure handling

| Failure | Behaviour |
|---|---|
| Worker crashes mid-submission | Lease expires; a replacement worker's stale fencing token fails the conditional write, so it reconciles instead of resubmitting |
| Timeout after clicking Submit | `OutcomeUnknown`; capacity stays consumed; reconciliation resolves to `Submitted` or `NeedsReview` |
| Employer changed the form | Signature mismatch at `dispatch`; submission refused; packet is rebuilt and re-approved |
| Mandate revoked after queueing | Cedar is re-evaluated at `begin`; the queued submission is refused |
| Two submissions race the daily cap | Capacity is reserved by a conditional transaction before the external write; the loser is refused |
| DynamoDB stream drops a record | The 5-minute outbox repair re-sends anything still `pending` |
| Queue message keeps failing | Redrive to the per-queue DLQ; `DeadLetterAlarm` and `WorkDeadLetterAlarm` fire |
| Model returns malformed output | Treated as no evidence; the field becomes a question, not a guess |

---

## Cost and operations

Designed to fit a $100 credit envelope:

- No NAT gateway, load balancer, or always-on compute.
- Per-user and global daily allowances for model and voice usage, **reserved before** the
  work is done rather than measured after.
- Source polling that skips unchanged feeds entirely.
- S3 lifecycle expiry on evidence and resumes; DynamoDB TTL on ephemeral items.
- `CostBudget` with alerts at 50% actual and 90% forecast.
- Least-privilege IAM per function — most visibly, the browser worker has no database
  access at all.
- CloudWatch alarms on both dead-letter queues.

Deployment is GitHub Actions via OIDC (`.github/workflows/ci-cd.yml`): tests → build →
`cloudformation deploy` → publish the UI to S3 → CloudFront invalidation → smoke test
against the live URL. No AWS keys are stored in the repository.
