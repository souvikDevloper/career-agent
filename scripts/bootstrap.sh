#!/usr/bin/env bash
# One-time AWS bootstrap for Career Agent CI/CD.
#
# Creates the GitHub OIDC provider, the deploy role that only this repository's
# main branch can assume, and the artifacts bucket - then stores the deploy
# parameters in SSM. Safe to re-run; it is a CloudFormation deploy plus an
# idempotent parameter write.
#
# Run it in AWS CloudShell (us-east-1) or anywhere the AWS CLI is configured:
#
#   ./scripts/bootstrap.sh you@example.com
#
# A brand-new AWS account cannot do this until account verification finishes -
# CloudShell and CloudFormation both refuse with "account verification is in
# progress". That wait is on AWS's side; re-run this once it clears.

set -euo pipefail

# Git Bash / MSYS rewrites arguments that start with a slash into Windows paths, so
# "/career-agent/deploy-parameters" would be stored as
# "C:/Program Files/Git/career-agent/deploy-parameters" and the deploy would never
# find it. Harmless everywhere else.
export MSYS2_ARG_CONV_EXCL='*' MSYS_NO_PATHCONV=1

EMAIL="${1:-}"
REGION="${2:-us-east-1}"
STACK="career-agent-bootstrap"
APP="career-agent"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -z "$EMAIL" ]; then
  echo "usage: $0 <your-email> [region]" >&2
  echo "  the email receives SES notifications, demo mail and budget alerts" >&2
  exit 2
fi

export AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"

echo "==> AWS account"
if ! aws sts get-caller-identity --query '[Account,Arn]' --output text; then
  echo "Could not call STS. Configure credentials first (aws configure), or run this in CloudShell." >&2
  exit 1
fi

# The GitHub OIDC provider is account-wide. If one already exists, a second
# CloudFormation-managed copy fails with EntityAlreadyExists, so reuse it.
if aws iam list-open-id-connect-providers --output text 2>/dev/null | grep -q "token.actions.githubusercontent.com"; then
  CREATE_OIDC="false"
  echo "==> GitHub OIDC provider already exists; reusing it"
else
  CREATE_OIDC="true"
fi

echo "==> Deploying $STACK in $REGION"
aws cloudformation deploy \
  --stack-name "$STACK" \
  --template-file "$ROOT/infra/bootstrap.yaml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --no-fail-on-empty-changeset \
  --parameter-overrides "CreateOidcProvider=$CREATE_OIDC"

echo "==> Storing deploy parameters"
aws ssm put-parameter --name "/$APP/deploy-parameters" --type String --overwrite \
  --value "SesSender=$EMAIL DemoInbox=$EMAIL AlertEmail=$EMAIL" >/dev/null

ROLE_ARN="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='DeployRoleArn'].OutputValue" --output text)"
BUCKET="$(aws cloudformation describe-stacks --stack-name "$STACK" \
  --query "Stacks[0].Outputs[?OutputKey=='ArtifactsBucket'].OutputValue" --output text)"

echo
echo "Deploy role      : $ROLE_ARN"
echo "Artifacts bucket : $BUCKET"

# The workflow pins the role ARN, so a different account silently breaks OIDC
# with "the web identity token provided could not be validated".
WANTED="$(grep -oE 'arn:aws:iam::[0-9]+:role/gha-career-agent-deploy' "$ROOT/.github/workflows/ci-cd.yml" | head -1 || true)"
if [ -n "$WANTED" ] && [ "$WANTED" != "$ROLE_ARN" ]; then
  echo
  echo "!! .github/workflows/ci-cd.yml expects:"
  echo "     $WANTED"
  echo "   but this account produced:"
  echo "     $ROLE_ARN"
  echo "   Update DEPLOY_ROLE in that workflow to the ARN above, commit and push,"
  echo "   or the deploy job will fail to assume the role."
fi

echo
echo "Next:"
echo "  1. Verify $EMAIL in Amazon SES (it starts in the sandbox)."
echo "  2. Push to main - or re-run the latest ci-cd workflow - to deploy."
echo "  3. Optional Telegram:"
echo "       aws ssm put-parameter --name /$APP/telegram-bot-token --type SecureString --value <token>"
