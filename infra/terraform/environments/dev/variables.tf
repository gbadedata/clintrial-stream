# =============================================================================
# infra/terraform/environments/dev/variables.tf
# =============================================================================
# Declares every input variable this configuration accepts.
#
# Variables are the configuration interface. Hard-coded values inside .tf files
# are anti-patterns — they prevent the same code from being reused for
# multiple environments. Every value that might differ between dev/staging/prod
# goes here as a variable.

# -----------------------------------------------------------------------------
# AWS connection
# -----------------------------------------------------------------------------
variable "aws_region" {
  description = "AWS region where all resources will be provisioned"
  type        = string
  default     = "eu-west-2"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-\\d$", var.aws_region))
    error_message = "aws_region must be a valid AWS region (e.g. eu-west-2)."
  }
}

variable "aws_profile" {
  description = "AWS CLI profile name (matches ~/.aws/credentials)"
  type        = string
  default     = "clintrial"
}

# -----------------------------------------------------------------------------
# Environment metadata
# -----------------------------------------------------------------------------
variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod."
  }
}

variable "project" {
  description = "Project name, used as a prefix for all resources"
  type        = string
  default     = "clintrial-stream"
}

# -----------------------------------------------------------------------------
# Alerting
# -----------------------------------------------------------------------------
variable "alarm_email" {
  description = "Email address that receives CloudWatch alarm notifications"
  type        = string

  validation {
    condition     = can(regex("^[\\w.+-]+@[\\w.-]+\\.\\w+$", var.alarm_email))
    error_message = "alarm_email must be a valid email address."
  }
}

# -----------------------------------------------------------------------------
# Kinesis stream configuration
# -----------------------------------------------------------------------------
variable "kinesis_shard_count" {
  description = "Number of shards in the Kinesis Data Stream. 1 shard = 1 MB/s ingest."
  type        = number
  default     = 2

  validation {
    condition     = var.kinesis_shard_count >= 1 && var.kinesis_shard_count <= 10
    error_message = "kinesis_shard_count must be between 1 and 10 for this project."
  }
}

variable "kinesis_retention_hours" {
  description = "How long Kinesis retains records (hours). Default 24, max 168 (7 days) for this project."
  type        = number
  default     = 24

  validation {
    condition     = var.kinesis_retention_hours >= 24 && var.kinesis_retention_hours <= 168
    error_message = "kinesis_retention_hours must be between 24 (1 day) and 168 (7 days) for this project."
  }
}

# -----------------------------------------------------------------------------
# DynamoDB configuration
# -----------------------------------------------------------------------------
variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode. PAY_PER_REQUEST suits irregular workloads."
  type        = string
  default     = "PAY_PER_REQUEST"

  validation {
    condition     = contains(["PAY_PER_REQUEST", "PROVISIONED"], var.dynamodb_billing_mode)
    error_message = "dynamodb_billing_mode must be PAY_PER_REQUEST or PROVISIONED."
  }
}
