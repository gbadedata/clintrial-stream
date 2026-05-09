# =============================================================================
# infra/terraform/modules/kinesis-stream/variables.tf
# =============================================================================
# Inputs accepted by the kinesis-stream module.
#
# Naming convention:
#   - Required variables have NO default
#   - Optional variables have a sensible default
#   - Every variable has a description and (where applicable) validation

# -----------------------------------------------------------------------------
# Required
# -----------------------------------------------------------------------------
variable "stream_name" {
  description = "Name of the Kinesis stream (must be unique within the AWS account/region)"
  type        = string

  validation {
    condition     = can(regex("^[a-zA-Z0-9_.-]{1,128}$", var.stream_name))
    error_message = "stream_name must be 1-128 chars, alphanumeric plus _.- only."
  }
}

# -----------------------------------------------------------------------------
# Stream configuration
# -----------------------------------------------------------------------------
variable "shard_count" {
  description = "Number of shards. 1 shard = 1 MB/s ingest, 2 MB/s read."
  type        = number
  default     = 2

  validation {
    condition     = var.shard_count >= 1 && var.shard_count <= 10
    error_message = "shard_count must be between 1 and 10 (cost guardrail for this project)."
  }
}

variable "retention_hours" {
  description = "How long Kinesis retains records. Min 24h, max 168h (7 days) for this project."
  type        = number
  default     = 24

  validation {
    condition     = var.retention_hours >= 24 && var.retention_hours <= 168
    error_message = "retention_hours must be between 24 and 168 for this project."
  }
}

# -----------------------------------------------------------------------------
# Observability
# -----------------------------------------------------------------------------
variable "iterator_age_threshold_ms" {
  description = "Threshold in ms for the IteratorAge alarm. Default 60s (consumer falling 1 min behind)."
  type        = number
  default     = 60000

  validation {
    condition     = var.iterator_age_threshold_ms > 0
    error_message = "iterator_age_threshold_ms must be greater than 0."
  }
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN to notify on alarm. If null, alarms still fire but no notifications sent."
  type        = string
  default     = null
}

# -----------------------------------------------------------------------------
# Tagging
# -----------------------------------------------------------------------------
variable "tags" {
  description = "Tags applied to every resource in this module"
  type        = map(string)
  default     = {}
}
