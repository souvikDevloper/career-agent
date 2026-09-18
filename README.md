<div align="center">

# Career Agent

**Your AI career agent that finds, applies and follows up — truthfully.**

Voice + chat job-search agent on AWS: discovers new openings while you're offline, explains fit with evidence from your resume,
prepares applications only from verified facts, submits under rules you control, and turns recruiter replies into deadlines and interview prep.

[Live app](#live-deployment) · [Architecture](docs/ARCHITECTURE.md) · [Demo script](docs/DEMO_SCRIPT.md) · [Hackathon writeup](docs/SUBMISSION.md)

![AWS](https://img.shields.io/badge/AWS-Serverless-FF9900?logo=amazonaws&logoColor=white)
![Bedrock](https://img.shields.io/badge/Amazon%20Bedrock-Nova%202%20Lite-7c3aed)
![Strands](https://img.shields.io/badge/Strands%20Agents-SDK-22d3ee)
![Cedar](https://img.shields.io/badge/Cedar-authorization-34d399)
![License](https://img.shields.io/badge/license-MIT-blue)

</div>

---

## Why

Students apply to hundreds of roles by hand, or hand their accounts to "auto-apply" bots that spray applications and invent answers.
Career Agent takes the useful part of automation — finding and filling — and adds what those bots lack: **explanations, hard rules, exact packets and receipts.**

## What it does

| | |
|---|---|
| 🎙️ **Talk to it** | Streaming speech-to-text (Amazon Transcribe) and neural spoken replies (Amazon Polly). Partial transcripts never trigger actions. |
| 📡 **Watches while you sleep** | EventBridge Scheduler polls sources every 5 minutes in AWS. Unchanged feeds cost zero model calls. |
| 🎯 **Explained fit** | Deterministic eligibility checks + a versioned 0–100 rubric. The model (Nova 2 Lite) only extracts evidence; every quote is verified against your resume. |
| 🧾 **Truthful packets** | The live employer form is read; each field maps to a verified fact, a saved answer, or becomes a question. Demographics and work authorization are never inferred. |
| 🛡️ **Rules the model can't bypass** | Three modes (review / auto > 80 / auto eligible) enforced by **Cedar** policies plus DynamoDB transactions: packet-hash approvals, mandates with expiry, daily caps, cooldowns. |
| 🤖 **Real submissions with receipts** | Playwright + Chromium on Lambda fills and submits, records the employer's reference and a screenshot. Timeouts become *confirming*, never a silent double-apply. |
| 📬 **Follows up** | Employer replies are matched by receipt, classified, and turned into dated tasks, reminders and grounded interview practice (voice mock interview). |
| 🔔 **One record, every channel** | Dashboard, email (SES) and Telegram approvals hit the same endpoint and the same application record. |

## Honest integration status

| Connector | Status | Capabilities |
|---|---|---|
| Northwind Labs careers | **Test environment** (fictional employer, clearly labeled) | discover · read form · fill · submit · reconcile · messages |
| Greenhouse public boards | **Verified live** | discover · read details — submitting requires the employer's key, so applying is a prepared **manual handoff** |
| Lever public boards | **Verified live** | discover · read details — submitting requires the employer's key, so applying is a prepared **manual handoff** |
| Ashby public boards | **Verified live** | discover · read details — submitting requires the employer's key, so applying is a prepared **manual handoff** |
| Email (SES) · Telegram | Needs setup per user | send · approvals |
| Gmail reply reading | Not enabled (restricted OAuth scopes need Google verification) | — |
| LinkedIn | **Manual handoff** — LinkedIn prohibits unauthorized automation | drafts and links only |

## Architecture

```
React (CloudFront/S3) ──► API Gateway (Cognito JWT) ──► API Lambda ──► DynamoDB (single table + transactional outbox)
        │                                                                   │ Streams
        └─ mic ─► Transcribe streaming (presigned)                          ▼
                                                            Relay ──► SQS work ──► Worker (Strands Agents + Bedrock Nova)
EventBridge Scheduler ──► Monitor (sources, reminders, repair)      ├─► SQS FIFO ──► Browser Lambda (Playwright) ⇄ Gate (Cedar)
Test employer portal ──HMAC webhook──► API                          └─► SQS notify ──► SES / Telegram
```

Full design, state machine, data model and failure handling: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## AWS services and why each is here

| Service | Role in the product |
|---|---|
| **Amazon Bedrock** (Nova 2 Lite, US inference profile) | Resume fact extraction with evidence, match evidence, grounded notes, reply classification, interview coaching |
| **Strands Agents SDK** | Agent loop over ten typed business tools |
| **Cedar** (`cedarpy`) | Authorization for every submission, approval, referral and profile action — parity-tested against a reference evaluator on 12k contexts |
| **AWS Lambda** | API, worker, relay, scheduler target, notifier, gate, test portal, and the Playwright browser (Node 22 + Chromium) |
| **Amazon DynamoDB** | Workflow state, immutable versions, daily ledger, idempotency, transactional outbox (Streams) |
| **Amazon SQS** | Work queue, FIFO submission queue grouped per user, notification queue — each with a DLQ |
| **Amazon EventBridge Scheduler** | 5-minute source monitor, reminders, outbox repair, judge-session cleanup |
| **Amazon Transcribe / Polly** | Streaming voice commands; neural voice replies (en-IN) |
| **Amazon Cognito** | Real users + short-lived, restricted example-workspace users |
| **Amazon S3 + CloudFront** | Private encrypted resumes/evidence; global UI + same-origin API routing (see *Front door* under Deploy — the HTTP API serves the UI when a distribution cannot be created) |
| **Amazon SES** | Email updates and approval links (links open the review; they never approve on GET) |
| **Secrets Manager, IAM, CloudWatch, Budgets** | HMAC secret, least-privilege roles, DLQ alarms, spend alerts |

## Try it

* **Example workspace** — one click on the landing page. A fictional applicant, a clearly labeled test employer, real model calls, real policy checks, real browser, real receipt. Publish a new opening and watch it become a verified submission.
* **Your own profile** — sign up, upload a PDF/DOCX resume, correct extracted facts, search, and prepare applications.

## Repository layout

```
backend/            Python 3.12 domain + Lambda handlers
  src/career_agent/ workflow (state machine, gate), scoring, policy (Cedar), agent (Strands), matching, applying,
                    discovery, resume, voice, notify, handlers/{api,worker,relay,scheduled,notifier,gate,portal}
  tests/            unit tests: state machine, 80/81 boundary, cap race, cooldown, revoked mandate, form change,
                    timeout after submit, worker crash, isolation, anti-hallucination, form parsing, Cedar parity
worker-browser/     Node 22 Playwright worker + real-Chromium test against the portal form
frontend/           React 19 + TypeScript (esbuild), hand-built design system
policies/           career_agent.cedar
infra/bootstrap.yaml GitHub OIDC deploy role + artifacts bucket
template.yaml       AWS SAM application stack
.github/workflows/  test → build → deploy → smoke test
```

## Develop

```bash
# backend tests (no AWS needed)
cd backend && pip install -r requirements-dev.txt && pytest -q

# browser worker test (real Chromium)
cd worker-browser && npm install && npx playwright-core install chromium && npm test

# UI with realistic fixtures
cd frontend && npm install && npm run build && node dev/mock-server.mjs   # http://localhost:5173
```

## Deploy

1. One time, in AWS CloudShell (us-east-1) or anywhere the AWS CLI is configured:
   ```bash
   git clone https://github.com/souvikDevloper/career-agent && cd career-agent
   ./scripts/bootstrap.sh you@example.com
   ```
   That creates the GitHub OIDC provider, the deploy role and the artifacts bucket, and
   stores the deploy parameters in SSM. It is safe to re-run, reuses an OIDC provider if
   the account already has one, and warns you if the role ARN it created does not match
   the `DEPLOY_ROLE` pinned in `.github/workflows/ci-cd.yml`.

   > A brand-new AWS account cannot run this until account verification completes —
   > CloudShell and CloudFormation both refuse with *"account verification is in
   > progress"*, which can take up to two days. Re-run it once that clears.

   Then verify the sender address in Amazon SES (it starts in the sandbox).
2. Push to `main`. GitHub Actions runs tests, assumes the deploy role via OIDC, builds manylinux artifacts, deploys `template.yaml`, publishes the UI, and smoke-tests the live URL.
   * **Front door.** CloudFront is the intended one. A brand-new AWS account cannot create a
     distribution until activation finishes — `CreateDistribution` returns 403 whatever IAM
     allows — so `UseCloudFront` defaults to `false` and the HTTP API serves the UI itself on
     the same origin. That keeps TLS, one origin, a private bucket and SPA deep links; it
     gives up edge caching. Add `UseCloudFront=true` to the SSM deploy parameters and redeploy
     once the account is activated.
3. Optional Telegram: `aws ssm put-parameter --name /career-agent/telegram-bot-token --type SecureString --value <token>` and redeploy.

## Live deployment

| | |
|---|---|
| App | _added after first deploy_ |
| Test employer portal | `<app>/portal` |
| Demo video | _added at submission_ |

## Cost

Designed for a $100 credit envelope: no NAT gateway, load balancer or always-on compute; per-user and global daily AI/voice allowances reserved before work; source polling that skips unchanged feeds; S3 lifecycle expiry; AWS Budget alerts at 50% and forecast 90%.

## Built with AI assistance

This project was built with Claude (Anthropic) as an AI pair programmer, as permitted by the hackathon rules.

## License

MIT
