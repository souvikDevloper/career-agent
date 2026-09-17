# Career Agent — hackathon writeup

**Track:** Ship It (deployed on AWS)
**Repository:** https://github.com/souvikDevloper/career-agent
**Live URL:** _see README_
**Team:** Souvik Ghosh

## Problem

Job hunting for students is a repetitive, lossy loop: find openings across many boards, decide whether you actually qualify, re-type the same answers into every form, and then lose track of replies, assessment deadlines and interview prep. "Auto-apply" tools make it worse — they spray applications, guess answers (including legal and demographic ones) and give no proof of what was sent.

## Solution

Career Agent is a voice- and chat-driven agent that runs in AWS while you're offline:

1. **Discovers** new openings on a declared schedule (EventBridge Scheduler, every 5 minutes) from supported sources.
2. **Explains fit** with a versioned 0–100 rubric; every requirement links to evidence quoted from your resume, and unverifiable model quotes are discarded.
3. **Prepares truthful applications** by reading the live employer form and mapping only verified facts or saved answers; unknown required questions are asked, never guessed.
4. **Submits under your rules** — review every packet, auto-apply strictly above 80, or auto-apply eligible jobs — enforced by Cedar policies plus DynamoDB transactions (packet-hash approvals, expiring mandates, daily caps, cooldowns).
5. **Proves it** with employer receipts and screenshots; an uncertain outcome is reconciled, never retried blindly.
6. **Follows up**: employer replies become classified stage changes, dated tasks, reminders and grounded voice interview practice.

Integrations are shown with their real status: the Northwind Labs employer is a **clearly labeled test environment** used to demonstrate real browser submissions; Greenhouse public boards are live for discovery with a prepared manual handoff for applying; LinkedIn is manual handoff because it prohibits unauthorized automation.

## How AWS is used

| Service | What it does in the demo |
|---|---|
| Amazon Bedrock — Nova 2 Lite | Resume fact extraction with evidence; match evidence; grounded application note; reply classification; interview questions and feedback |
| Strands Agents SDK | Agent loop with ten typed business tools (no shell/fetch/credential tools) |
| Cedar | Authorization for submissions, approvals, referrals, profile publishing; parity-tested |
| AWS Lambda | API, background worker, stream relay, scheduler target, notifier, submission gate, test employer portal, Playwright/Chromium browser |
| Amazon DynamoDB | Single-table workflow state, immutable versions, daily ledger, idempotency, transactional outbox via Streams |
| Amazon SQS | Work queue, FIFO submission queue grouped per user, notification queue, DLQs |
| Amazon EventBridge Scheduler | 5-minute monitor, reminders, outbox repair, cleanup |
| Amazon Transcribe (streaming) / Amazon Polly (Neural) | Voice commands; spoken replies; voice mock interview |
| Amazon Cognito | Users and restricted short-lived example-workspace sessions |
| Amazon S3 + CloudFront | Private encrypted files; global HTTPS UI with same-origin API routing |
| Amazon SES | Email updates and approval links |
| Secrets Manager, IAM, CloudWatch, AWS Budgets, CloudFormation/SAM | HMAC secret, least privilege, alarms, spend alerts, reproducible deploys via GitHub OIDC |

## What I learned

* Designing agent autonomy as an **authorization problem** (Cedar + transactions) instead of a prompt problem.
* The **transactional outbox** pattern with DynamoDB Streams and why duplicate SQS deliveries must be harmless.
* The **external-write boundary**: recording "dispatched" before clicking Submit so a crash leads to reconciliation, not double application.
* Running **Playwright with Chromium on Lambda** instead of an always-on EC2 worker to stay inside the free-tier budget.
* AWS **event-stream framing** for Transcribe WebSockets from the browser with presigned, role-scoped URLs.

## AI tools used

Claude (Anthropic) was used as an AI pair programmer for design review, implementation and tests.
