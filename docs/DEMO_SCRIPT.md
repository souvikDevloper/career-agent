# Three-minute demo video — script

Goal: show a real problem, a working product and visible AWS usage (the rules require AWS usage to be shown in the video).
Record at 1440p, browser zoom 90%, dark UI. Keep the AWS console tabs pre-opened.

| Time | Screen | Say (short) |
|---|---|---|
| 0:00–0:15 | Landing page hero | "Students apply to hundreds of jobs by hand, or hand their accounts to bots that invent answers. Career Agent automates the useful part — truthfully." |
| 0:15–0:30 | Click **Try the example workspace** → Command center | "This is an isolated example workspace: a fictional applicant and a clearly labeled test employer. Everything else is real — Bedrock, Cedar, a real browser." |
| 0:30–0:55 | Agent page, tap mic: *"Find backend internships that fit my resume"* | "Voice goes straight to Amazon Transcribe over a presigned WebSocket. A Strands agent on Bedrock Nova calls typed tools — results stream in with scores." Open one match drawer: "Every must-have links to the exact line in the resume. The model only extracts evidence; the rubric is computed in code." |
| 0:55–1:10 | Settings → **Auto-apply above 80** | "Three modes. This one needs an explicit mandate with an expiry. Caps and cooldowns are reserved atomically in DynamoDB; Cedar decides right before the click." |
| 1:10–1:50 | Command center → **Publish opening** (Cloud Engineer Intern) | "A new role appears on the test employer. EventBridge normally checks every 5 minutes — I'll trigger the same pipeline now." Pipeline: Detected → Scored 86 → Prepared → Authorized → Receipt. "It read the live form, mapped verified facts, declined to self-identify gender, and an isolated Playwright browser on Lambda submitted it." |
| 1:50–2:10 | Application detail: receipt NWL-…, packet with source badges, timeline, attempt with Cedar decision | "The approval is bound to this SHA-256 packet hash. The timeline shows the Cedar policy that allowed it. If the network had timed out after clicking, it would reconcile instead of re-submitting." |
| 2:10–2:30 | **Send OA invite** → task with deadline; Tasks page | "The employer replies through a signed webhook. Nova classifies it, the deadline must be quoted from the message, and a reminder is scheduled." |
| 2:30–2:45 | Interview practice → answer by voice → feedback | "Practice questions come from this job's requirements; feedback quotes what I actually said. Polly reads replies aloud." |
| 2:45–3:00 | AWS console: CloudFormation stack resources, Lambda list, DynamoDB items, CloudWatch log line with correlation id; GitHub Actions green run | "It's all serverless on AWS — Lambda, DynamoDB streams outbox, SQS FIFO, EventBridge Scheduler, Bedrock, Transcribe, Polly, Cognito, CloudFront — deployed from GitHub with OIDC. Career Agent: autonomy you can audit." |

**Backup plan:** if the model is throttled during recording, the UI shows the keyword-extractor badge honestly; re-record the matching segment rather than hide it.
