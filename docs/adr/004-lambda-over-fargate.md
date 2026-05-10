# ADR-004: Lambda over Fargate for the consumer

**Status:** Accepted

## Context

Each event written to the Kinesis stream needs to be:

1. Validated against the domain schema
2. Persisted to DynamoDB for the hot path
3. Fanned out to S3 for the cold archive

The consumer that does this work could run as either a Kinesis-triggered AWS Lambda function or a long-running container on ECS Fargate.

## Decision

Run the consumer as **AWS Lambda** with a Kinesis event source mapping.

## Alternatives considered

**ECS Fargate (long-running container)**

- Container reads from Kinesis using the Kinesis Client Library (KCL) and DynamoDB for shard coordination
- Suits sustained high-throughput workloads where Lambda's per-invocation overhead matters
- Operational overhead: container lifecycle, deployment pipeline, health checks, log shipping, autoscaling rules
- Always-on cost - at low traffic the container sits idle but billed

**EC2 with KCL**

- Maximum control, lowest per-record cost at very high scale
- Operationally heaviest of the three - patching, AMIs, autoscaling groups, all the things Fargate already abstracts
- Out of scope for a platform optimised for clarity

**EventBridge Pipes**

- Serverless source-to-target plumbing with optional filtering and transformation
- Limits on transformation complexity - domain validation logic lives more naturally in code
- Useful complement, not a replacement: a future iteration could use Pipes for the Kinesis-to-S3 archive path

## Consequences

**Positive**

- Lambda's Kinesis event source mapping handles shard tracking, batching, retries, and DLQ delivery
- Per-shard parallelism is automatic - one Lambda invocation per shard at a time, with `ParallelizationFactor` to fan out further if needed
- Idle cost is genuinely zero. The platform can be left provisioned overnight without burning money

**Negative**

- 15-minute hard limit per invocation. Not a concern for per-event work, would be for batch reprocessing - that uses S3+Glue instead
- Cold starts add 100-500ms to the first invocation after idle. Acceptable for a consumer; would be unacceptable for a synchronous API path
- Memory cap of 10 GB and ephemeral storage cap of 10 GB. Both fine for our payload sizes; flagged for future ML enrichment workloads

## Future revisit triggers

Move to Fargate (or KCL on EC2) if any of these become true:

- Sustained throughput exceeds 1 MB/s per shard for hours at a time (Lambda invocation overhead becomes a meaningful share of cost)
- Per-event processing legitimately needs more than 15 minutes
- We need persistent in-memory state across events that's expensive to rebuild
