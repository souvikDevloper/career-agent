# AWS support case text

Evidence gathered 2026-09-18 05:42 UTC from account `686090305719`, calling as
`arn:aws:iam::686090305719:user/souvik-cli` (AdministratorAccess).

Do not paste access keys, secrets or passwords into a support case. Nothing below contains any.

---

## Where to file

**Support Center → Create case → Account and billing**
- Service: **Account**
- Category: **Activation**
- Severity: General guidance (or the highest your plan allows)

File **one** case covering both Bedrock and CloudFront — they are the same underlying
account hold, and splitting them across two cases usually means two separate queues.

SES production access is **not** a support case: it is a separate form at
**SES console → Account dashboard → Request production access**.

---

## Subject

```
Account 686090305719 still blocked: Bedrock runtime "Operation not allowed" and CloudFront "account must be verified"
```

---

## Body

```
Hello,

Account 686090305719 (new account, India) is still under an account-level restriction
that blocks two services, despite an earlier email saying my services were active.
I have verified this from the CLI today and included the exact errors below.

I am a student building a project for a hackathon submission and the deadline is close.
Everything else in my application works; these two blocks are the only thing preventing a
complete demo.

--------------------------------------------------------------------
1) Amazon Bedrock - every runtime invocation fails
--------------------------------------------------------------------

All Bedrock runtime calls fail with a ValidationException, in every region I try:

  $ aws bedrock-runtime converse --region us-east-1 \
      --model-id us.amazon.nova-2-lite-v1:0 \
      --messages '[{"role":"user","content":[{"text":"hi"}]}]' \
      --inference-config '{"maxTokens":10}'

  An error occurred (ValidationException) when calling the Converse operation:
  Operation not allowed

Same error in us-west-2. Same error with a base model id rather than an inference
profile (amazon.nova-lite-v1:0), which rules out an inference-profile problem.

What makes me think this is an account-level restriction rather than a permissions or
model-access problem:

  - The Bedrock CONTROL plane works fine from the same credentials:
      $ aws bedrock list-foundation-models --region us-east-1
      -> returns 115 models
  - The caller has AdministratorAccess.
  - The failure is ValidationException "Operation not allowed", not
    AccessDeniedException. A missing model-access grant returns AccessDeniedException
    with a message naming the model, which is not what I am getting.

Could you confirm whether a restriction is applied to this account for Bedrock runtime,
and lift it? If model access also needs granting for Amazon Nova, please tell me and I
will request it in the console.

--------------------------------------------------------------------
2) CloudFront - cannot create a distribution
--------------------------------------------------------------------

  $ aws cloudfront create-distribution --distribution-config ...

  An error occurred (AccessDenied) when calling the CreateDistribution operation:
  Your account must be verified before you can add new CloudFront resources. To verify
  your account, please contact AWS Support
  (https://console.aws.amazon.com/support/home#/) and include this error message.

I am including that error message as the text instructs. Read-only CloudFront calls
(ListDistributions) succeed, and every other CloudFront resource type (Origin Access
Control, Response Headers Policy, CloudFront Function) creates normally through
CloudFormation. Only CreateDistribution is refused.

I have worked around this by serving the site through API Gateway instead, so this is
not blocking me as hard as Bedrock is, but I would like the account verified so I can
use CloudFront as intended.

--------------------------------------------------------------------
Context
--------------------------------------------------------------------

- Payment verification already succeeded: the UPI AutoPay authorisation was charged and
  refunded as expected.
- I previously received an email saying my services were now active, but the two errors
  above are from today and are still failing.
- If this is a review against a previous account of mine, please tell me what you need
  from me to clear it - I will provide any identity or payment verification required.

Thank you,
Souvik
```

---

## If you already have a case open, reply on it instead

Adding a reply keeps the history together and usually gets a faster response than a new
case, which starts at the back of the queue.

```
Following up with fresh evidence from today (2026-09-18, account 686090305719).

Both blocks are still in place:

1) Bedrock runtime - every region, every model id:
   ValidationException: Operation not allowed
   (bedrock-runtime Converse, us-east-1 and us-west-2, with both
   us.amazon.nova-2-lite-v1:0 and amazon.nova-lite-v1:0)

   The Bedrock control plane works from the same credentials -
   ListFoundationModels returns 115 models - and the caller has AdministratorAccess,
   so this looks like an account-level restriction rather than IAM or model access.
   The error is ValidationException, not AccessDeniedException.

2) CloudFront CreateDistribution:
   AccessDenied: Your account must be verified before you can add new CloudFront
   resources. To verify your account, please contact AWS Support and include this
   error message.

I received an email saying my services were active, but these calls still fail. Could
you confirm what is still outstanding on the account and what you need from me?

Thank you,
Souvik
```

---

## Separately: SES production access

Current state is the sandbox default (200 messages/24h, 1/sec), confirmed by
`aws ses get-send-quota`. That is a **form, not a support case**:

**SES console → Account dashboard → Request production access**

Use case text that works for this project:

```
Career Agent is a job-search assistant I built for a hackathon. It sends two kinds of
mail, both to the person who signed up and only to them:

1. An approval request when the agent has prepared a job application, so the person can
   approve or reject it before anything is submitted.
2. A notification when an employer replies, or when a deadline is approaching.

Volume is very low - under 50 messages a day, to a handful of my own test accounts and
hackathon judges who have signed up themselves.

Recipients are never imported or purchased. Every address belongs to someone who created
an account and verified their email. Every message includes a link to notification
settings where they can turn email off, and deleting an account deletes the address.
I handle bounces and complaints via SES event notifications and stop sending to any
address that bounces or complains.
```

---

## What is not worth asking for

**The Cognito signup code going missing is not an AWS fault and not worth a case.**
The user pool uses `COGNITO_DEFAULT`, which sends from `no-reply@verificationemail.com`.
Cognito accepts the send and reports delivery - the mail is going out, Gmail is filing it
under Spam or Promotions. Moving Cognito onto SES only helps once SES is out of the
sandbox, and even then judges do not need it: the demo's example workspace requires no
signup at all.
