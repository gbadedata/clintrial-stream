# =============================================================================
# infra/terraform/modules/kinesis-stream/outputs.tf
# =============================================================================
# Outputs from the kinesis-stream module. The calling environment uses these
# to wire the stream into other components (Lambda triggers, IAM role
# attachments, etc.)

output "stream_name" {
  description = "Name of the Kinesis stream"
  value       = aws_kinesis_stream.this.name
}

output "stream_arn" {
  description = "ARN of the Kinesis stream"
  value       = aws_kinesis_stream.this.arn
}

output "stream_id" {
  description = "ID of the Kinesis stream (same as name)"
  value       = aws_kinesis_stream.this.id
}

output "shard_count" {
  description = "Number of shards in the stream"
  value       = aws_kinesis_stream.this.shard_count
}

output "producer_policy_arn" {
  description = "ARN of the IAM policy for producers (PutRecord/PutRecords)"
  value       = aws_iam_policy.producer.arn
}

output "consumer_policy_arn" {
  description = "ARN of the IAM policy for consumers (GetRecords/GetShardIterator)"
  value       = aws_iam_policy.consumer.arn
}

output "alarm_arns" {
  description = "ARNs of the three CloudWatch alarms created by this module"
  value = {
    iterator_age              = aws_cloudwatch_metric_alarm.iterator_age.arn
    write_throughput_exceeded = aws_cloudwatch_metric_alarm.write_throughput_exceeded.arn
    read_throughput_exceeded  = aws_cloudwatch_metric_alarm.read_throughput_exceeded.arn
  }
}
