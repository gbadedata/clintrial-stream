#!/usr/bin/env bash
# =============================================================================
# scripts/bootstrap-terraform-backend.sh
# =============================================================================
# Provisions the Terraform remote state backend resources (S3 bucket for state
# files + DynamoDB table for state locking).
#
# This script is run ONCE per AWS account, before `terraform init`. After this
# bootstrap, all infrastructure is managed by Terraform itself.
#
# Why bootstrap with the AWS CLI instead of Terraform? Chicken-and-egg: Terraform
# needs a state backend to operate, but the backend doesn't exist yet. We solve
# this by creating the backend with raw AWS CLI calls. Once the backend exists,
# every other resource (including the backend's own IAM policies, lifecycle
# rules, etc.) can be managed by Terraform.
#
# Idempotent: safe to re-run. Skips resources that already exist.
#
# Usage:
#   ./scripts/bootstrap-terraform-backend.sh
#
# Requirements:
#   - AWS CLI v2 configured with profile `clintrial`
#   - Region eu-west-2
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration (override via environment variables if needed)
# -----------------------------------------------------------------------------
AWS_PROFILE="${AWS_PROFILE:-clintrial}"
AWS_REGION="${AWS_REGION:-eu-west-2}"
ACCOUNT_ID="${ACCOUNT_ID:-677276115158}"
PROJECT="${PROJECT:-clintrial-stream}"

BUCKET_NAME="${PROJECT}-tfstate-${ACCOUNT_ID}"
LOCK_TABLE_NAME="${PROJECT}-tflock"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
# Color codes (only when stdout is a TTY)
if [[ -t 1 ]]; then
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  RED='\033[0;31m'
  BLUE='\033[0;34m'
  RESET='\033[0m'
else
  GREEN=''; YELLOW=''; RED=''; BLUE=''; RESET=''
fi

info()    { printf "${BLUE}ℹ${RESET}  %s\n" "$1"; }
ok()      { printf "${GREEN}✓${RESET}  %s\n" "$1"; }
warn()    { printf "${YELLOW}⚠${RESET}  %s\n" "$1"; }
fatal()   { printf "${RED}✗${RESET}  %s\n" "$1" >&2; exit 1; }
heading() { printf "\n${BLUE}=== %s ===${RESET}\n" "$1"; }

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
heading "Pre-flight checks"

command -v aws >/dev/null || fatal "aws CLI not found"

# Verify caller identity matches expected account
caller_account=$(aws sts get-caller-identity --query Account --output text --profile "$AWS_PROFILE")
if [[ "$caller_account" != "$ACCOUNT_ID" ]]; then
  fatal "Connected to wrong AWS account. Expected $ACCOUNT_ID, got $caller_account"
fi

caller_arn=$(aws sts get-caller-identity --query Arn --output text --profile "$AWS_PROFILE")
ok "Authenticated as: $caller_arn"

if [[ "$caller_arn" == *":root" ]]; then
  fatal "Refusing to run as root. Use a dedicated IAM user."
fi

ok "AWS account: $ACCOUNT_ID"
ok "Region: $AWS_REGION"
ok "Profile: $AWS_PROFILE"

# -----------------------------------------------------------------------------
# Step 1 — Create the S3 bucket for Terraform state
# -----------------------------------------------------------------------------
heading "Step 1 — S3 bucket for Terraform state"

if aws s3api head-bucket --bucket "$BUCKET_NAME" --profile "$AWS_PROFILE" 2>/dev/null; then
  ok "Bucket $BUCKET_NAME already exists, skipping creation"
else
  info "Creating bucket $BUCKET_NAME..."

  # Note: us-east-1 doesn't accept LocationConstraint; every other region does
  if [[ "$AWS_REGION" == "us-east-1" ]]; then
    aws s3api create-bucket \
      --bucket "$BUCKET_NAME" \
      --region "$AWS_REGION" \
      --profile "$AWS_PROFILE" >/dev/null
  else
    aws s3api create-bucket \
      --bucket "$BUCKET_NAME" \
      --region "$AWS_REGION" \
      --create-bucket-configuration LocationConstraint="$AWS_REGION" \
      --profile "$AWS_PROFILE" >/dev/null
  fi

  ok "Bucket created"
fi

# -----------------------------------------------------------------------------
# Step 2 — Enable versioning on the bucket
# -----------------------------------------------------------------------------
# Versioning is non-negotiable for Terraform state buckets. If state ever gets
# corrupted (concurrent apply, partial network failure, accidental delete), we
# can roll back to a previous version.

info "Enabling bucket versioning..."
aws s3api put-bucket-versioning \
  --bucket "$BUCKET_NAME" \
  --versioning-configuration Status=Enabled \
  --profile "$AWS_PROFILE"
ok "Versioning enabled"

# -----------------------------------------------------------------------------
# Step 3 — Enable default encryption (SSE-S3 / AES-256)
# -----------------------------------------------------------------------------
# Terraform state contains sensitive resource metadata (sometimes secrets in
# outputs). Encryption at rest is mandatory for compliance and best practice.
# SSE-S3 (AES-256) is the simplest option and free. KMS adds key rotation
# but costs $1/month per key. For a portfolio project, SSE-S3 is fine.

info "Enabling default encryption (AES-256)..."
aws s3api put-bucket-encryption \
  --bucket "$BUCKET_NAME" \
  --server-side-encryption-configuration '{
    "Rules": [
      {
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        },
        "BucketKeyEnabled": true
      }
    ]
  }' \
  --profile "$AWS_PROFILE"
ok "Encryption enabled"

# -----------------------------------------------------------------------------
# Step 4 — Block all public access
# -----------------------------------------------------------------------------
# Belt-and-braces: even if someone misconfigures bucket ACLs or policies,
# this account-level block prevents public exposure. State files MUST never
# be public — they often contain secrets.

info "Blocking all public access..."
aws s3api put-public-access-block \
  --bucket "$BUCKET_NAME" \
  --public-access-block-configuration '{
    "BlockPublicAcls": true,
    "IgnorePublicAcls": true,
    "BlockPublicPolicy": true,
    "RestrictPublicBuckets": true
  }' \
  --profile "$AWS_PROFILE"
ok "Public access blocked"

# -----------------------------------------------------------------------------
# Step 5 — Lifecycle rule: clean up old state versions
# -----------------------------------------------------------------------------
# Versioning preserves every state mutation forever — over years that grows
# storage cost. This rule keeps the last 30 days of versions and removes
# anything older. Recent versions stay accessible for rollback.

info "Setting lifecycle rule (keep last 30 days of state versions)..."
aws s3api put-bucket-lifecycle-configuration \
  --bucket "$BUCKET_NAME" \
  --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "expire-old-state-versions",
        "Status": "Enabled",
        "Filter": {"Prefix": ""},
        "NoncurrentVersionExpiration": {
          "NoncurrentDays": 30
        },
        "AbortIncompleteMultipartUpload": {
          "DaysAfterInitiation": 7
        }
      }
    ]
  }' \
  --profile "$AWS_PROFILE"
ok "Lifecycle rule applied"

# -----------------------------------------------------------------------------
# Step 6 — Tag the bucket
# -----------------------------------------------------------------------------
# Tagging every resource enables cost allocation, ownership tracking, and
# automated cleanup. Tags are an early-stage discipline that pays off later.

info "Tagging bucket..."
aws s3api put-bucket-tagging \
  --bucket "$BUCKET_NAME" \
  --tagging "TagSet=[
    {Key=Project,Value=$PROJECT},
    {Key=Component,Value=terraform-backend},
    {Key=Environment,Value=shared},
    {Key=ManagedBy,Value=bootstrap-script},
    {Key=Owner,Value=gbadedata}
  ]" \
  --profile "$AWS_PROFILE"
ok "Bucket tagged"

# -----------------------------------------------------------------------------
# Step 7 — Create the DynamoDB lock table
# -----------------------------------------------------------------------------
# Terraform uses this table to coordinate concurrent applies. When two engineers
# (or CI runners) try to apply at the same time, the second one waits for the
# first to finish. Without it, you get state corruption.
#
# The table only needs:
#   - A single string partition key called LockID
#   - PAY_PER_REQUEST billing (we only write once per apply)

heading "Step 7 — DynamoDB lock table"

if aws dynamodb describe-table \
     --table-name "$LOCK_TABLE_NAME" \
     --region "$AWS_REGION" \
     --profile "$AWS_PROFILE" >/dev/null 2>&1; then
  ok "Table $LOCK_TABLE_NAME already exists, skipping creation"
else
  info "Creating table $LOCK_TABLE_NAME..."
  aws dynamodb create-table \
    --table-name "$LOCK_TABLE_NAME" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --tags \
      Key=Project,Value="$PROJECT" \
      Key=Component,Value=terraform-backend \
      Key=Environment,Value=shared \
      Key=ManagedBy,Value=bootstrap-script \
      Key=Owner,Value=gbadedata \
    --region "$AWS_REGION" \
    --profile "$AWS_PROFILE" >/dev/null

  info "Waiting for table to become ACTIVE..."
  aws dynamodb wait table-exists \
    --table-name "$LOCK_TABLE_NAME" \
    --region "$AWS_REGION" \
    --profile "$AWS_PROFILE"

  ok "Table created and active"
fi

# Enable point-in-time recovery (free for first 35 days; $0.20/GB after)
# Negligible cost for a tiny lock table; valuable insurance.
info "Enabling point-in-time recovery on lock table..."
aws dynamodb update-continuous-backups \
  --table-name "$LOCK_TABLE_NAME" \
  --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" >/dev/null
ok "Point-in-time recovery enabled"

# -----------------------------------------------------------------------------
# Step 8 — Output the backend configuration
# -----------------------------------------------------------------------------
heading "Backend configuration"

cat <<SUMMARY

The Terraform remote state backend is ready. Use these values in your
backend.tf file:

  bucket         = "$BUCKET_NAME"
  key            = "<environment>/terraform.tfstate"
  region         = "$AWS_REGION"
  dynamodb_table = "$LOCK_TABLE_NAME"
  encrypt        = true

For example, the dev environment in infra/terraform/environments/dev/backend.tf
will reference:
  bucket = "$BUCKET_NAME"
  key    = "environments/dev/terraform.tfstate"

Verify with:
  aws s3 ls s3://$BUCKET_NAME --profile $AWS_PROFILE
  aws dynamodb describe-table --table-name $LOCK_TABLE_NAME --region $AWS_REGION --profile $AWS_PROFILE

SUMMARY

ok "Bootstrap complete"
