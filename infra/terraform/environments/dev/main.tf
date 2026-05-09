# =============================================================================
# infra/terraform/environments/dev/main.tf
# =============================================================================
# The dev environment composition. This file wires together all the reusable
# modules (Kinesis, DynamoDB, S3, Lambda, etc.) into a working environment.
#
# Naming convention: every resource is named "${var.project}-${var.environment}"
# This guarantees uniqueness across AWS accounts that contain multiple environments.
#
# Modules are added incrementally:
#   - Step 5.4: Kinesis stream module ✓ (this file)
#   - Step 5.5: DynamoDB table module
#   - Step 5.6: S3 audit bucket module
#   - Step 5.7: Lambda consumer module
#   - Step 5.8: Cognito module

# -----------------------------------------------------------------------------
# Local values (computed once, referenced everywhere)
# -----------------------------------------------------------------------------
locals {
  # Standard naming prefix for all resources
  name_prefix = "${var.project}-${var.environment}"

  # Tags merged with provider default_tags (local additions, not overrides)
  common_tags = {
    Component = "infrastructure"
  }
}

# -----------------------------------------------------------------------------
# Account context (useful for IAM policies, ARN construction, etc.)
# -----------------------------------------------------------------------------
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# -----------------------------------------------------------------------------
# SNS topic for infrastructure alarms
# -----------------------------------------------------------------------------
# A single SNS topic that all CloudWatch alarms publish to. The dev environment
# subscribes one email; production would subscribe PagerDuty / Slack / etc.
resource "aws_sns_topic" "alarms" {
  name = "${local.name_prefix}-alarms"

  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-alarms"
  })
}

resource "aws_sns_topic_subscription" "alarms_email" {
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

# -----------------------------------------------------------------------------
# Kinesis Data Stream (events ingestion)
# -----------------------------------------------------------------------------
module "events_stream" {
  source = "../../modules/kinesis-stream"

  stream_name               = "${local.name_prefix}-events"
  shard_count               = var.kinesis_shard_count
  retention_hours           = var.kinesis_retention_hours
  iterator_age_threshold_ms = 60000
  alarm_sns_topic_arn       = aws_sns_topic.alarms.arn

  tags = local.common_tags
}
