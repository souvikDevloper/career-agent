# Development and deployment

[README](../README.md) · [Architecture](ARCHITECTURE.md) · [Browser Companion](../browser-companion/README.md)

## Prerequisites

- Python 3.12 for the backend and deployment build.
- Node.js 22.17 or later for the frontend and browser worker.
- Git and Playwright-managed Chromium for browser tests.
- AWS CLI credentials and deployment permissions for deployment; ordinary backend tests do not require a live AWS account.
- Bash for infrastructure scripts. On Windows, use Git Bash or WSL for those scripts.

Unless stated otherwise, run commands from the repository root.

## Backend checks

Create a virtual environment:

```text
python -m venv .venv
```

Activate it using `.venv\Scripts\Activate.ps1` in PowerShell, or `source .venv/bin/activate` in Bash on Linux/macOS. Then run:

```text
python -m pip install -r backend/requirements-dev.txt
python -m ruff check backend/src backend/tests
python -m pytest -c backend/pyproject.toml backend/tests -q
```

The pytest configuration adds the backend source and test directories to the Python path. Native dependencies such as Cedar can depend on the platform; Linux CI is the reference environment for the full dependency set.

## Frontend

```text
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

For the fixture-backed UI, run this **from the frontend directory** after building:

```text
node dev/mock-server.mjs
```

The mock server is a development aid. Its fixtures do not prove a live model call or employer submission.

## Browser tests

```text
npm --prefix worker-browser ci
npx --prefix worker-browser playwright-core install chromium
npm --prefix worker-browser test
node --test browser-companion/test/*.test.mjs
```

Linux machines may also need Playwright's system dependencies, as installed in CI with `install --with-deps chromium`. Worker tests use controlled application forms. Companion tests exercise employer-shaped fixtures and mocked extension APIs. See the [extension guide](../browser-companion/README.md) for live installation and pairing.

## Model configuration

The runtime accepts a native Bedrock adapter or a compatible endpoint adapter. Model access depends on the AWS account and region; copying a model identifier does not grant access to it.

The project's GLM-5 Bedrock configuration is:

```text
ModelProvider=openai
ModelApiBase=https://bedrock-mantle.us-east-1.api.aws/v1
FallbackModelId=zai.glm-5
```

Here, `openai` names the API protocol used by the Strands adapter. Inference is served by Amazon Bedrock. `FallbackModelId` is the existing parameter name for the compatible-endpoint model.

For the native adapter:

```text
ModelProvider=bedrock
ModelId=<an-accessible-Bedrock-model-or-inference-profile>
```

The native route also requires IAM permission for the selected model. The template's current permissions target its configured Nova model family and inference profiles; changing models can require an infrastructure permission update.

| SAM parameter | Runtime variable | Purpose |
| --- | --- | --- |
| `ModelProvider` | `MODEL_PROVIDER` | Select the client adapter |
| `ModelId` | `MODEL_ID` | Native Bedrock model identifier |
| `ModelApiBase` | `MODEL_API_BASE` | Compatible endpoint base URL |
| `FallbackModelId` | `FALLBACK_MODEL_ID` | Compatible endpoint model identifier |
| Derived from stack name | `MODEL_API_KEY_PARAM` | SSM parameter holding the compatible endpoint key |

Store the key as an SSM **SecureString** at `/<stack-name>/model-api-key`. Do not put it in the deployment-parameter string or commit it to Git. The application reads it server-side.

## Deployment

The deployment definition is [template.yaml](../template.yaml). The pipeline is [ci-cd.yml](../.github/workflows/ci-cd.yml).

1. Configure the AWS CLI for the intended account and region.
2. Review [infra/bootstrap.yaml](../infra/bootstrap.yaml), especially the GitHub repository and branch allowed to assume the deployment role.
3. For a new installation, run the bootstrap script in Bash:

   ```bash
   ./scripts/bootstrap.sh you@example.com us-east-1
   ```

4. Use the reported role ARN as `DEPLOY_ROLE` in the workflow. The checked-in ARN belongs to the project's deployment; a fork must configure its own.
5. Configure the complete parameter string in `/career-agent/deploy-parameters`, including the selected model route and source settings. The bootstrap script overwrites this parameter with its initial email settings, so do not rerun it casually against a configured installation.
6. Store required model or connector secrets separately, verify notification identities in SES, and confirm model access.
7. Push reviewed changes to `main` or run the workflow manually. It tests, builds Lambda artifacts, deploys the stack, publishes frontend assets, and runs smoke checks.

The pipeline deploys changes on `main`; successful pull-request checks alone do not deploy. An unpacked Browser Companion installation must be refreshed separately.

### Selected infrastructure parameters

| Parameter | Meaning |
| --- | --- |
| `GreenhouseBoards`, `LeverBoards`, `AshbyBoards` | Configured public board names |
| `WorkdayBoards` | Tenant, pod, and career-site configurations |
| `OracleBoards` | Tenant, site, and optional country configurations |
| `AmazonBoards` | Country and optional query configurations |
| `AdzunaBoards` | Optional aggregator configuration; credentials are also required |
| `EnableTestEmployer` | Include the fictional employer fixture; disabled by default |
| `UseCloudFront` | Select CloudFront or API-backed frontend serving |
| `SesSender`, `AlertEmail` | Notification sender and operational alert destination |
| `MonthlyBudgetUsd` | Budget notification threshold; not a spending stop |

Read the template for accepted formats and defaults before changing a parameter.

## Operational verification

Verify each layer separately after deployment:

1. **Availability:** application load, authentication, and deployment smoke result.
2. **Discovery:** a known company/role query, returned source status, and watch scheduling.
3. **Preparation:** selected resume version, saved answers, packet contents, and authorization state.
4. **Browser execution:** companion connection, intended employer session, field handling, and final timeline.
5. **Outcome:** actual employer confirmation or an explicitly uncertain result, followed separately by notification delivery.

Inspect CloudWatch and dead-letter alarms for failed work. Queue age and backlog matter alongside error counts. Raising all worker concurrency can consume API capacity; inspect the account quota and event-source mappings first.

Use a controlled test employer or a deliberately authorized real application when testing submission. Fixture success and smoke-test success do not prove that an arbitrary external application was accepted.
