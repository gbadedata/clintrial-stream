# `kinesis-stream` module

A reusable Terraform module that provisions a Kinesis Data Stream with built-in observability and least-privilege IAM policies.

## What it creates

| Resource | Purpose |
|---|---|
| `aws_kinesis_stream` | The stream itself (PROVISIONED mode, KMS encryption, shard-level metrics) |
| `aws_cloudwatch_metric_alarm.iterator_age` | Fires when consumers fall behind |
| `aws_cloudwatch_metric_alarm.write_throughput_exceeded` | Fires when producers are throttled |
| `aws_cloudwatch_metric_alarm.read_throughput_exceeded` | Fires when consumers are throttled |
| `aws_iam_policy.producer` | Allows `PutRecord` / `PutRecords` on this stream |
| `aws_iam_policy.consumer` | Allows `GetRecords` / `GetShardIterator` on this stream |

## Usage

```hcl
module "events_stream" {
  source = "../../modules/kinesis-stream"

  stream_name              = "clintrial-stream-events-dev"
  shard_count              = 2
  retention_hours          = 24
  iterator_age_threshold_ms = 60000
  alarm_sns_topic_arn      = aws_sns_topic.alerts.arn

  tags = {
    Environment = "dev"
    Component   = "ingestion"
  }
}
```

Then attach the producer / consumer policies to whatever IAM roles need them:

```hcl
resource "aws_iam_role_policy_attachment" "producer_kinesis" {
  role       = aws_iam_role.producer.name
  policy_arn = module.events_stream.producer_policy_arn
}
```

## Inputs

| Name | Description | Type | Default | Required |
|---|---|---|---|:---:|
| `stream_name` | Name of the Kinesis stream | `string` | n/a | yes |
| `shard_count` | Number of shards (1-10) | `number` | `2` | no |
| `retention_hours` | Retention period (24-168 hours) | `number` | `24` | no |
| `iterator_age_threshold_ms` | Alarm threshold for consumer lag | `number` | `60000` | no |
| `alarm_sns_topic_arn` | SNS topic for alarm notifications | `string` | `null` | no |
| `tags` | Tags applied to all resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|---|---|
| `stream_name` | Stream name |
| `stream_arn` | Stream ARN |
| `stream_id` | Stream ID (same as name) |
| `shard_count` | Number of shards |
| `producer_policy_arn` | ARN of producer IAM policy |
| `consumer_policy_arn` | ARN of consumer IAM policy |
| `alarm_arns` | Map of alarm ARNs by type |

## Cost

| Component | Monthly cost (eu-west-2, 2 shards, 24h retention) |
|---|---|
| Kinesis shards | $22.32 ($0.015/shard-hour × 2 × 744h) |
| Data ingestion | $0.014/GB (negligible for our demo volumes) |
| Enhanced metrics | $0.04/month ($0.02/shard × 2) |
| CloudWatch alarms | $0.30/month ($0.10/alarm × 3) |
| **Total** | **~$22.66/month** |

For demos: provision, run for an hour, destroy. Hourly cost ~$0.03.

## Design notes

### Why PROVISIONED instead of ON_DEMAND?

`ON_DEMAND` is ~$36/month minimum (it bills for capacity even when idle). `PROVISIONED` with 2 shards is ~$22/month and gives us full control. For a demo workload, the auto-scaling of `ON_DEMAND` doesn't add value.

In production, switching to `ON_DEMAND` is one variable flip — `stream_mode = "ON_DEMAND"` and remove `shard_count`.

### Why three alarms?

These are the three failure modes that production Kinesis pipelines actually hit:

1. **IteratorAge** — consumer can't keep up. Events expire from the stream after `retention_hours`.
2. **WriteProvisionedThroughputExceeded** — producers are sending too fast. Leads to dropped events if not retried.
3. **ReadProvisionedThroughputExceeded** — consumers are reading too aggressively. Each shard supports ~5 reads/second.

Skipping these alarms is the most common production-readiness gap in Kinesis tutorials.

### Why separate producer and consumer policies?

Least privilege. If a producer's IAM role is compromised, the attacker can only spam events — they can't read existing data or destroy the stream. Same for consumers in reverse.

A single "kinesis-full-access" policy attached to everything is simpler to write but expands blast radius enormously.
