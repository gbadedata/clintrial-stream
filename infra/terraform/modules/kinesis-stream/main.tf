# =============================================================================
# infra/terraform/modules/kinesis-stream/main.tf
# =============================================================================
# Reusable module for a Kinesis Data Stream with built-in observability and
# least-privilege IAM policies.
#
# What this module creates:
#   1. The Kinesis Data Stream itself
#   2. CloudWatch alarms for the three failure modes that matter:
#      a. IteratorAge — consumer falling behind (events older than threshold)
#      b. WriteProvisionedThroughputExceeded — producers being throttled
#      c. ReadProvisionedThroughputExceeded — consumers being throttled
#   3. IAM policies (producer-only, consumer-only) for least-privilege access
#
# What this module does NOT create:
#   - IAM roles (created by the calling environment so they can be reused)
#   - SNS topics (created at environment level, multiple alarms share them)
#   - Kinesis Firehose / S3 archival (separate module)

# -----------------------------------------------------------------------------
# The stream
# -----------------------------------------------------------------------------
resource "aws_kinesis_stream" "this" {
  name             = var.stream_name
  shard_count      = var.shard_count
  retention_period = var.retention_hours

  # Enhanced metrics — emits per-shard metrics to CloudWatch.
  # Costs $0.02/shard/month; worth it for observability into hot shards.
  shard_level_metrics = [
    "IncomingBytes",
    "IncomingRecords",
    "OutgoingBytes",
    "OutgoingRecords",
    "WriteProvisionedThroughputExceeded",
    "ReadProvisionedThroughputExceeded",
    "IteratorAgeMilliseconds",
  ]

  # Server-side encryption with the AWS-managed key for Kinesis.
  # Free; protects against snapshot/backup leakage.
  encryption_type = "KMS"
  kms_key_id      = "alias/aws/kinesis"

  # PROVISIONED (we control the shard count) vs ON_DEMAND (AWS auto-scales).
  # PROVISIONED is cheaper for steady workloads; ON_DEMAND wins for spiky
  # workloads. For demo: PROVISIONED with 2 shards is fine.
  stream_mode_details {
    stream_mode = "PROVISIONED"
  }

  tags = merge(var.tags, {
    Name      = var.stream_name
    Component = "ingestion"
  })
}

# -----------------------------------------------------------------------------
# CloudWatch alarm: consumer falling behind
# -----------------------------------------------------------------------------
# IteratorAgeMilliseconds is the age of the oldest record in the shard that
# hasn't yet been read by a consumer. If this grows unbounded, the consumer
# is too slow and events will be lost (after retention_hours).
#
# Threshold: 60_000 ms (1 minute) is a reasonable default for low-volume demos.
# Production systems on critical pipelines might alarm at 5-10 seconds.
resource "aws_cloudwatch_metric_alarm" "iterator_age" {
  alarm_name          = "${var.stream_name}-iterator-age-high"
  alarm_description   = "Consumer is falling behind on stream ${var.stream_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "GetRecords.IteratorAgeMilliseconds"
  namespace           = "AWS/Kinesis"
  period              = 60
  statistic           = "Maximum"
  threshold           = var.iterator_age_threshold_ms
  treat_missing_data  = "notBreaching"

  dimensions = {
    StreamName = aws_kinesis_stream.this.name
  }

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  tags = merge(var.tags, {
    Component = "observability"
  })
}

# -----------------------------------------------------------------------------
# CloudWatch alarm: producers being throttled (write throughput exceeded)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "write_throughput_exceeded" {
  alarm_name          = "${var.stream_name}-write-throttling"
  alarm_description   = "Producers are exceeding write throughput on ${var.stream_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "WriteProvisionedThroughputExceeded"
  namespace           = "AWS/Kinesis"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    StreamName = aws_kinesis_stream.this.name
  }

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  tags = merge(var.tags, {
    Component = "observability"
  })
}

# -----------------------------------------------------------------------------
# CloudWatch alarm: consumers being throttled
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "read_throughput_exceeded" {
  alarm_name          = "${var.stream_name}-read-throttling"
  alarm_description   = "Consumers are exceeding read throughput on ${var.stream_name}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ReadProvisionedThroughputExceeded"
  namespace           = "AWS/Kinesis"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    StreamName = aws_kinesis_stream.this.name
  }

  alarm_actions = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []
  ok_actions    = var.alarm_sns_topic_arn != null ? [var.alarm_sns_topic_arn] : []

  tags = merge(var.tags, {
    Component = "observability"
  })
}

# -----------------------------------------------------------------------------
# IAM policy: producer (PutRecord, PutRecords only)
# -----------------------------------------------------------------------------
# This policy is attached to whatever IAM role represents a producer. The
# producer can write events to the stream but cannot:
#   - Read events back
#   - Modify or delete the stream
#   - List other streams
#
# Even if producer credentials leak, the blast radius is limited to spam
# (extra events) — no data exfiltration, no destruction.
resource "aws_iam_policy" "producer" {
  name        = "${var.stream_name}-producer"
  description = "Allows writing events to the ${var.stream_name} Kinesis stream"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kinesis:PutRecord",
          "kinesis:PutRecords",
          "kinesis:DescribeStream",
          "kinesis:DescribeStreamSummary",
        ]
        Resource = aws_kinesis_stream.this.arn
      },
      # Allow describing limits — clients use this to detect throttling
      {
        Effect = "Allow"
        Action = [
          "kinesis:DescribeLimits",
        ]
        Resource = "*"
      },
    ]
  })

  tags = merge(var.tags, {
    Component = "security"
  })
}

# -----------------------------------------------------------------------------
# IAM policy: consumer (GetRecords, GetShardIterator, etc.)
# -----------------------------------------------------------------------------
# Lambda consumers and other readers attach this policy. It allows reading
# events but not writing or destroying.
resource "aws_iam_policy" "consumer" {
  name        = "${var.stream_name}-consumer"
  description = "Allows reading events from the ${var.stream_name} Kinesis stream"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "kinesis:GetRecords",
          "kinesis:GetShardIterator",
          "kinesis:DescribeStream",
          "kinesis:DescribeStreamSummary",
          "kinesis:ListShards",
          "kinesis:SubscribeToShard",
        ]
        Resource = aws_kinesis_stream.this.arn
      },
    ]
  })

  tags = merge(var.tags, {
    Component = "security"
  })
}
