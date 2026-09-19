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

## Reply to send when support says the account is already active

Checked 2026-09-18 07:02 UTC, after support reported the account active. Two separate
things are wrong, and only one of them is theirs.

**1. The hold is still on.** CloudFront is the unambiguous proof, because its error names
the cause rather than hiding behind a generic one:

```
AccessDenied: Your account must be verified before you can add new CloudFront resources.
```

**2. Model access was never granted** - a second, separate gap:

```
$ aws bedrock get-foundation-model-availability --model-id amazon.nova-lite-v1:0
  authorizationStatus:     NOT_AUTHORIZED
  agreementAvailability:   AVAILABLE
  entitlementAvailability: AVAILABLE
  regionAvailability:      AVAILABLE

$ aws bedrock get-use-case-for-model-access
  ResourceNotFoundException: You have not filled out the request form.
```

0 of 7 models authorised. Amazon's own models cannot be granted through
CreateFoundationModelAgreement ("Agreement not supported for this model"), so it has to be
the console.

Send this:

```
Thank you for the update, but the account is not active yet. Checked just now
(2026-09-18, 07:02 UTC, account 686090305719):

  $ aws cloudfront create-distribution ...
  AccessDenied: Your account must be verified before you can add new CloudFront
  resources. To verify your account, please contact AWS Support and include this
  error message.

That error names account verification directly, so the hold is still applied.

Bedrock runtime is also still refusing every call, in every region, for every model
family, with ValidationException "Operation not allowed" - while the Bedrock control
plane answers normally from the same credentials.

Separately, I can see that model access has never been granted on this account:

  get-foundation-model-availability for amazon.nova-lite-v1:0 returns
  authorizationStatus NOT_AUTHORIZED, with agreementAvailability AVAILABLE,
  entitlementAvailability AVAILABLE and regionAvailability AVAILABLE.
  get-use-case-for-model-access returns "You have not filled out the request form."

Could you confirm two things:

1. Is the account verification hold still applied? The CloudFront error says it is.
2. Can model access be granted while that hold is in place, or does the hold have to be
   lifted first? I would like to enable Amazon Nova now so there is nothing else in the
   way once verification completes.

I am a student with a hackathon deadline in two days.

Thank you,
Souvik
```

---

## Email aws-verification@amazon.com as well as the case

us-east-2 returns a different, more specific error than the other regions, and it names a
dedicated address. Support cases queue; this address is the verification team directly.

```
An error occurred (AccessDeniedException) when calling the InvokeModel operation:
Your account is currently being verified. Verification normally takes less than 2 hours.
Until your account is verified, you may not have access to this operation. If you are
still receiving this message after more than 2 hours, please let us know by writing to
aws-verification@amazon.com. We appreciate your patience.
```

Send this, as the message itself instructs:

```
To: aws-verification@amazon.com
Subject: Account 686090305719 - still unverified after several days, Bedrock blocked

Hello,

Account 686090305719 has been showing "Your account is currently being verified" for
several days, not the "less than 2 hours" the message describes. Your own error text
asks me to write to this address if that happens, so I am.

Bedrock runtime is unusable as a result. In us-east-2:

  AccessDeniedException: Your account is currently being verified. Verification normally
  takes less than 2 hours. Until your account is verified, you may not have access to
  this operation.

In us-east-1, us-west-2, eu-central-1, ap-northeast-1 and ca-central-1 the same calls
return ValidationException "Operation not allowed" instead. The Bedrock control plane
works from the same credentials (ListFoundationModels returns 115 models) and my IAM user
has AdministratorAccess, so this is the account hold rather than permissions.

CloudFront CreateDistribution is refused by the same hold:

  AccessDenied: Your account must be verified before you can add new CloudFront
  resources. To verify your account, please contact AWS Support and include this
  error message.

My payment verification already succeeded - the UPI AutoPay authorisation was charged and
refunded. I also received an email saying my services were active, but the errors above
are from today.

I am a student with a hackathon deadline. Please tell me what is outstanding and what you
need from me.

Thank you,
Souvik
```

---

## What I tested, so you can say it in the case if asked

Every Bedrock runtime path is blocked identically on this account:

| Probe | Result |
|---|---|
| `Converse`, us-east-1, `us.amazon.nova-2-lite-v1:0` | ValidationException: Operation not allowed |
| `Converse`, us-west-2, same model | ValidationException: Operation not allowed |
| `InvokeModel`, us-east-2 | AccessDeniedException: account is currently being verified |
| `InvokeModel`, eu-central-1 / ap-northeast-1 / ca-central-1 | ValidationException: Operation not allowed |
| `InvokeModel`, `amazon.nova-lite-v1:0` | ValidationException: Operation not allowed |
| `InvokeModel`, `anthropic.claude-3-haiku` | ValidationException: Operation not allowed |
| `InvokeModel`, `meta.llama3-8b-instruct` | ValidationException: Operation not allowed |
| `InvokeModel`, `mistral.mistral-7b-instruct` | ValidationException: Operation not allowed |
| `InvokeModel`, `amazon.titan-text-express-v1` | ResourceNotFoundException: model has reached end of life |
| `ListFoundationModels` (control plane) | 200, 115 models |

The Titan row is the useful one: a *different* error proves the request reaches Bedrock
and is validated before the block is applied. So this is not IAM, not model access, and
not a bad model id - the service accepts the call and then refuses the operation.

**SageMaker is not a workaround.** Endpoint quota on this account is 0 for every instance
type except `ml.t2.medium` (2 vCPU, 4 GB, no GPU), which cannot host a useful model:

    ml.g5.xlarge for endpoint usage   = 0
    ml.g4dn.xlarge for endpoint usage = 0
    ml.m5.large for endpoint usage    = 0
    ml.t2.medium for endpoint usage   = 2

If you want to mention it in the case, the ask is the same hold: the account restriction
zeroes SageMaker hosting quota as well as Bedrock runtime.

---

## Strongest single piece of evidence: AgentCore is zeroed against non-zero defaults

Measured 2026-09-19 in us-east-1. Every Bedrock AgentCore quota on this account is set to
zero, while the service's published defaults are not:

    Total concurrent active browser sessions   default 1000   applied 0
    Total Browser profiles per account         default  100   applied 0
    Total Browser tool configurations          default 1000   applied 0
    Total concurrent code interpreter sessions default 1000   applied 0
    Active session workloads per account       default 5000   applied 0

This matters more than the Bedrock runtime denials, because it cannot be explained as a
model-access or region question:

- The control plane answers normally. `bedrock-agentcore-control list-browsers` returns
  `{"browserSummaries": []}` - no AccessDenied, so the account is entitled to the service.
- The data plane refuses. `bedrock-agentcore start-browser-session` returns
  `ServiceQuotaExceededException: maxBrowserSessions limit exceeded`.
- Service Quotas will not accept an increase request, because there is nothing to increase:
  it answers "You must provide a quota value greater than the default quota value of 1000.0".
  The account is below default, not asking to exceed it.

So this is not a quota the customer can request. A service whose default is 1000 reading 0
on a single account is an account-level suppression, which is the same hold that produces
the Bedrock runtime denials and the CloudFront block. Asking support to raise a quota is the
wrong ask and will be closed; the ask is to lift the account restriction.

Suggested wording:

> Every Bedrock AgentCore quota on account 686090305719 reads 0 while the service defaults
> are 1000/100/5000. The control plane (`list-browsers`) succeeds, so the account is
> entitled to the service, but `StartBrowserSession` fails with ServiceQuotaExceeded and
> Service Quotas refuses an increase request because 0 is below the default. This is not a
> quota request - please lift the account-level restriction that is zeroing these.

---

## What is not worth asking for

**The Cognito signup code going missing is not an AWS fault and not worth a case.**
The user pool uses `COGNITO_DEFAULT`, which sends from `no-reply@verificationemail.com`.
Cognito accepts the send and reports delivery - the mail is going out, Gmail is filing it
under Spam or Promotions. Moving Cognito onto SES only helps once SES is out of the
sandbox, and even then judges do not need it: the demo's example workspace requires no
signup at all.
