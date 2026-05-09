# =============================================================================
# infra/terraform/environments/dev/outputs.tf
# =============================================================================
# Outputs are values exported from this Terraform configuration that other
# tools, scripts, or environments can consume.
#
# Common uses:
#   - Print useful info after `terraform apply` (account ID, region, ARNs)
#   - Pass values into application config (.env files, parameter store)
#   - Reference outputs from another Terraform configuration

# -----------------------------------------------------------------------------
# Environment metadata
# -----------------------------------------------------------------------------
output "aws_account_id" {
  description = "The AWS account ID where resources are provisioned"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "The AWS region used by this environment"
  value       = data.aws_region.current.name
}

output "environment" {
  description = "Environment name"
  value       = var.environment
}

output "name_prefix" {
  description = "Standard naming prefix used for all resources"
  value       = local.name_prefix
}

# -----------------------------------------------------------------------------
# SNS
# -----------------------------------------------------------------------------
output "alarms_topic_arn" {
  description = "ARN of the SNS topic that receives all CloudWatch alarms"
  value       = aws_sns_topic.alarms.arn
}

# -----------------------------------------------------------------------------
# Kinesis
# -----------------------------------------------------------------------------
output "events_stream_name" {
  description = "Name of the Kinesis events stream"
  value       = module.events_stream.stream_name
}

output "events_stream_arn" {
  description = "ARN of the Kinesis events stream"
  value       = module.events_stream.stream_arn
}

output "events_stream_producer_policy_arn" {
  description = "IAM policy ARN for producers of the events stream"
  value       = module.events_stream.producer_policy_arn
}

output "events_stream_consumer_policy_arn" {
  description = "IAM policy ARN for consumers of the events stream"
  value       = module.events_stream.consumer_policy_arn
}
