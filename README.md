<div align="center">

# Career Agent

**A job-search agent that finds, explains and prepares applications — and can prove every claim it makes.**

Discovers openings across configured employer feeds while you're offline · explains fit against the exact lines in your resume ·
prepares applications only from facts you verified · submits under rules a model cannot talk its way past ·
turns recruiter replies into deadlines and interview prep.

**[▶ Live app](https://frg3ei3pc0.execute-api.us-east-1.amazonaws.com)** — one click, no signup

[Architecture](docs/ARCHITECTURE.md) · [Demo script](docs/DEMO_SCRIPT.md) · [Submission](docs/SUBMISSION.md)

![AWS](https://img.shields.io/badge/AWS-Serverless-FF9900?logo=amazonaws&logoColor=white)
![Bedrock](https://img.shields.io/badge/Amazon%20Bedrock-agent%20runtime-7b5cff)
![Strands](https://img.shields.io/badge/Strands%20Agents-SDK-4cc9f0)
![Cedar](https://img.shields.io/badge/Cedar-authorization-4ade80)
![MCP](https://img.shields.io/badge/MCP-OAuth%202.1-f5a9dd)
![Tests](https://img.shields.io/badge/tests-259%20passing-4ade80)
![License](https://img.shields.io/badge/license-MIT-blue)

</div>

---

## The problem

Students send hundreds of applications by hand, or hand their credentials to an "auto-apply" bot that
sprays submissions and invents answers to questions it was never told the answer to.

Both fail for the same reason: **neither can show its work.** You cannot tell why a role was picked,
what was written on your behalf, or whether a claim in your application is true.

Career Agent automates the finding and the filling, and adds the part those tools skip — an explanation
for every score, a rule the model cannot bypass, an exact packet you approve before anything is sent, and
a receipt afterwards.

---

## What it does

| | |
|---|---|
| 🔎 **Finds real openings** | Configured employer feeds plus direct Google and Microsoft searches. Returned results distinguish current responses, cached postings and source failures. |
| 🎯 **Explains fit, with evidence** | A versioned 0–100 rubric. Every required skill links to the line in your resume that proves it — or is reported as a gap. Quotes are verified against your actual resume text before they are shown. |
| 🧾 **Prepares truthful packets** | Reads the employer's form, maps each field to a verified fact or a saved answer, and turns anything it cannot evidence into a question for you. Demographics and work authorisation are never inferred. |
| 🛡️ **Rules a model can't bypass** | **Cedar** policies plus DynamoDB transactions enforce approval modes, packet-hash approvals, mandates with expiry, daily caps and cooldowns. Authorisation is backend code, never the prompt. |
| 🤖 **Submits with receipts** | Playwright on Lambda fills and submits, then records the employer's reference and a screenshot. A timeout becomes *confirming*, never a silent double-apply. |
| 🎙️ **Talks** | Streaming speech-to-text (Transcribe) and neural replies (Polly). Partial transcripts never trigger actions. |
| 🔌 **Works from your client** | An **MCP server** with **OAuth 2.1** serves the agent's own tool registry to any MCP client, authenticated as you. |
| 📬 **Follows up** | Employer replies are matched by receipt, classified, and become dated tasks, reminders and grounded interview practice. |

---

## Try it in 30 seconds

Open the [live app](https://frg3ei3pc0.execute-api.us-east-1.amazonaws.com) and click **Try the example workspace**.

No signup. You get an isolated workspace with a fictional applicant and a clearly labelled test employer —
but real model calls, real policy checks, a real browser submission and a real receipt.

Ask the agent:

```
Find Amazon engineering jobs in Bengaluru
Find Microsoft internships
```

Both requests query supported employer sources. Google and Microsoft use direct careers search;
source failures are reported separately from a successful search with no matching openings.
Searches stay within the requested employer, role and location. See the dated
[source verification and coverage limits](docs/search-reliability.md).

### Set up the continuous application loop

1. Upload and review your resume in **Profile**, then add reusable application answers.
2. In **Settings**, choose review, auto-apply strictly above 80, or auto-apply to eligible jobs.
   Set your daily cap and preferences. Renew an older test-only mandate to authorize live supported destinations.
3. Enable/reload the [Browser Companion 1.1.0](browser-companion/README.md), refresh the app,
   and click **Connect this browser** in Settings. The connection lasts seven days.
4. Create a watch with your company, role, location and desired interval through chat, final voice input,
   or Matches. Intervals run on the existing five-minute scheduler ticks.
5. Verify the notification email address in Settings. New matches, preparation, approval needs,
   browser attention and confirmed submissions produce distinct notifications.

Discovery and preparation run in AWS while you are offline. Authenticated employer forms run in
the connected browser, which must stay open and signed in. Authorized applications open automatically,
fill from the approved resume version and saved answers, and submit only after a fresh policy check.
Unknown required answers, login and CAPTCHA require attention; no unsupported answer is invented.
An uncertain submission is reconciled rather than submitted again. Employer confirmation emails
are sent by employers; Career Agent records page confirmations and its own notifications, and does
not claim to read Gmail without a configured inbox integration.

---

## Architecture

```
React 19 (S3, private)                  ┌──────────────────── EventBridge Scheduler
        │                               │                     every 5 min
        ▼                               ▼
   API Gateway ──JWT (Cognito)──► API Lambda ──► DynamoDB ──Streams──► Relay ──► SQS
        │                               │        single table                      │
        │                               │        + transactional outbox            ▼
        ├─ /api/mcp  ── OAuth 2.1 ──────┤                                  Worker Lambda
        │                               │                                  Strands + Bedrock
        └─ /portal   ── HMAC webhook ───┘                                          │
                                                          ┌───────────────────────┼─────────────┐
                                                          ▼                       ▼             ▼
                                                    SQS FIFO             SQS notify      Cedar gate
                                                          │                       │             │
                                                   Browser Lambda          SES / Telegram   allow/deny
                                                   (Playwright)                             at submit time
```

Two paths, deliberately separated:

- **Synchronous** — anything a person waits on. Writes to DynamoDB and returns. Never calls the model or a browser inline.
- **Asynchronous** — everything slow or risky. The API commits a state change *and* an outbox row in **one transaction**;
  the relay turns that row into an SQS message. A browser worker can time out without losing a state change,
  because the state change was committed before the work was dispatched.

Full design, state machine, data model and failure handling: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**

---

## Connector coverage

Configured public job-feed connectors and direct Google/Microsoft careers searches provide discovery.
Results report whether a response is fresh, cached, incomplete or unavailable.

| Connector | Employers | Capabilities |
|---|---|---|
| **Amazon Jobs** | Amazon | discover · read details · country filter · structured intern flag |
| **Google Careers** | Google and YouTube | direct search · employer seniority filters · role/location filtering |
| **Microsoft Careers** | Microsoft | direct search · entry-level facet · paginated results and details |
| **Oracle HCM** | JPMorgan Chase | discover · read details · country filter at ingestion |
| **Workday** | PayPal, NVIDIA, Salesforce, Adobe, Autodesk, HP | discover · read details |
| **Greenhouse** | Stripe, Databricks, MongoDB, Elastic, Coinbase, Airbnb, Twilio, Reddit, Dropbox, GitLab, Rubrik | discover · read details |
| **Lever** | Match Group | discover · read details · employer-declared work mode |
| **Ashby** | Linear, PostHog | discover · read details |
| **Northwind Labs** | *fictional test employer, clearly labelled* | discover · read form · **fill · submit · reconcile** |

Cloud-browser routes and authenticated Browser Companion routes are distinct. The companion uses
your existing employer login without copying passwords or cookies to the backend. Its multistep
regressions use local Amazon/Workday-shaped forms; those tests do not claim a real employer submission.

### What is deliberately not here

**LinkedIn.** Their User Agreement prohibits automated access, and an account doing it gets banned —
the user's own account, for a feature meant to help them.

**Unsupported employer endpoints.** Some careers APIs return `429` or `403` to a server on the first
request. They work in a browser because of session context. Getting past that means forging browser
sessions to evade rate limiting.

The line is not whether data is public. It is **whether the operator serves it to programs.**
Greenhouse, Lever, Ashby, Workday, Oracle and Amazon do. The others deliberately do not.

---

## How truthfulness is enforced

Not by asking the model nicely. Four mechanisms, each with tests:

1. **Quote verification** — every quote the model attributes to your resume is checked against the actual
   resume text. Unverifiable quotes are dropped, not shown.
2. **Number grounding** — a figure in a generated cover note must appear in the source material
   ([`applying.py`](backend/src/career_agent/applying.py)). Invented metrics never reach a packet.
3. **Unknowns become questions** — a form field with no verified answer is surfaced to you, never guessed.
   Demographics and work authorisation are never inferred.
4. **Packet-hash approval** — you approve a specific packet hash. If anything changes between approval
   and submission, the transaction fails rather than sending something you did not see.

And when the model is unreachable, the app says so and falls back to a keyword extractor — it does not
pretend to have scored with AI.

---

## Authorization

Cedar policies plus DynamoDB conditional writes. The model has no say in any of it.

| Control | Enforced by |
|---|---|
| Approval mode (review / auto > 80 / auto eligible) | Cedar policy, evaluated at submit time |
| Daily cap, cooldown | DynamoDB conditional write — a race cannot exceed the cap |
| Mandate expiry | Cedar policy + clock |
| Packet integrity | Hash compared inside the submitting transaction |
| Ownership | Derived from the Cognito JWT; **no tool accepts a user id** |

The agent's tools are a fixed, typed registry: no shell, no arbitrary fetch, no credential access, no
policy editing. The same registry is served over MCP — and `approve_application` is **withheld** from
that surface, because submitting is the one irreversible act and a tool call from another model cannot
evidence that a person asked for it.

---

## MCP server

`POST /api/mcp` serves the agent's tool registry to any Model Context Protocol client, with full
**OAuth 2.1** — dynamic client registration (RFC 7591), PKCE S256, single-use codes.

```bash
# Discovery, registration, PKCE exchange and a tool call all work against the live deployment
curl -s https://frg3ei3pc0.execute-api.us-east-1.amazonaws.com/.well-known/oauth-protected-resource
```

One tool registry, two front doors: `describe_tool()` builds the schema for both the Bedrock tool loop
and MCP from the same docstrings, so a tool cannot be described one way to the voice agent and another
way to a connector.

---

## AWS services

Lambda · API Gateway (HTTP API) · DynamoDB (single table + streams) · S3 · SQS (standard + FIFO) ·
Cognito · EventBridge Scheduler · Bedrock · Transcribe · Polly · SES · Secrets Manager · SSM Parameter
Store · CloudWatch · SNS · Budgets · IAM · STS · CloudFront

Plus two AWS open-source projects: **Strands Agents SDK** (the agent runtime) and **Cedar** (authorization).

No VPC, no NAT gateway, no load balancer, no always-on compute — a deliberate cost decision, not an omission.

---

## Develop

```bash
# Backend tests — no AWS account needed
cd backend && pip install -r requirements-dev.txt && pytest -q      # 259 passing

# Browser worker against a real Chromium
cd worker-browser && npm install && npx playwright-core install chromium && npm test

# UI with realistic fixtures
cd frontend && npm install && npm run build && node dev/mock-server.mjs   # http://localhost:5173
```

The test suite is written from real payloads and from bugs that actually shipped — a board that returns
one placeholder id for all 665 of its postings, a search that answered a question about one employer with
jobs from another, an index key that made every live board invisible. Each of those has a test named after
what went wrong.

---

## Deploy

```bash
git clone https://github.com/souvikDevloper/career-agent && cd career-agent
./scripts/bootstrap.sh you@example.com     # OIDC provider, deploy role, artifacts bucket, SSM parameters
git push origin main                        # CI: test → build → deploy → smoke test
```

Configuration lives in one SSM parameter (`/career-agent/deploy-parameters`):

```
GreenhouseBoards=stripe,databricks,...  WorkdayBoards=paypal:wd1:jobs,...
OracleBoards=jpmc:CX_1001:IN            AmazonBoards=IND
ModelProvider=bedrock
```

---

## Project layout

```
backend/                 Python 3.12 · 7,400 lines · 259 tests
  src/career_agent/
    workflow.py          state machine, transactional outbox, usage ledger
    scoring.py           versioned rubric, eligibility filters
    policy.py            Cedar engine + reference implementation
    agent.py             Strands tool registry (one registry, two front doors)
    mcp.py               MCP server
    oauth.py             OAuth 2.1 authorization server
    llm.py               model access, provider-agnostic
    sources/             amazon · oraclehcm · workday · greenhouse · lever · ashby · portal
    handlers/            api · worker · relay · scheduled · notifier · gate · portal · web
worker-browser/          Node 22 Playwright worker
frontend/                React 19 + TypeScript on esbuild · 4,700 lines
policies/                career_agent.cedar
template.yaml            AWS SAM stack
```

---

## Cost

Built for a $100 credit envelope and measured against it: no always-on compute, per-user and global daily
model allowances **reserved before work starts** (a transaction, so a race cannot exceed them), polling
that skips unchanged feeds, lazy description fetching, S3 lifecycle expiry, and AWS Budget alerts at 50%
and forecast 90%.

---

## Known limitations

Stated here rather than discovered by a judge:

- **Live employer submission is a handoff, not an automation.** Only the labelled test portal is submitted to end-to-end.
- **Email is SES sandbox** — delivery is limited to verified addresses until production access is granted.
- **CloudFront is off.** A new AWS account cannot create a distribution until verification completes, so the
  HTTP API serves the UI on the same origin. Same TLS, same origin, private bucket, SPA deep links — it
  gives up edge caching only. One parameter turns it on.
- **Coverage is bounded by configured feeds and direct employer adapters.** It does not represent every opening on the market.

---

## Built with AI assistance

Built with Claude (Anthropic) as a pair programmer, as the hackathon rules permit.

## License

MIT
