# ADR-001: Kinesis Data Streams over SQS for ingestion

**Status:** Accepted

## Context

ClinTrial-Stream needs to ingest a continuous flow of clinical trial events (adverse events, enrollment changes, lab results) from many trial sites. The platform must:

- Preserve per-patient ordering - an enrollment must be visible before any adverse event for that patient
- Allow multiple independent consumers to read the same events (real-time dashboard, S3 archive, alerting)
- Replay events from a point in time when a downstream consumer needs to be rebuilt

## Decision

Use **Amazon Kinesis Data Streams** as the primary ingestion bus.

## Alternatives considered

**Amazon SQS (standard queue)**

- No ordering guarantees within a queue, even FIFO queues only guarantee per-message-group ordering and cap throughput at 300 messages/second per group
- Each message can be consumed once - to fan out to multiple consumers we'd need either SNS-fan-out-to-SQS (more moving parts) or to push to S3 separately
- No replay - once a message is acknowledged it's gone

**Amazon MSK (managed Kafka)**

- Closest functional match to Kinesis, with broader ecosystem tooling
- Operationally heavier: managing brokers, topics, partitions, ZooKeeper/KRaft, schema registry
- Higher minimum cost (single-node MSK Serverless ≈ $50/month base before data)
- For a portfolio platform, the operational overhead outweighs the slightly richer ecosystem

**EventBridge**

- Optimised for event routing across services, not high-volume per-record ingestion
- Per-event pricing model ($1/M events) becomes expensive at scale
- No replay or retention beyond 24 hours of archive

## Consequences

**Positive**

- Per-shard ordering preserved using `patient_id` as the partition key
- Multiple independent consumers via shard iterators - Lambda for hot path, Firehose for S3 archive, both reading the same stream
- 24-hour retention by default (extendable to 7 days) supports replay during incidents

**Negative**

- Shard provisioning is manual - adding shards requires monitoring `IteratorAgeMilliseconds` and resharding (or moving to ON_DEMAND mode)
- Per-shard cost (~$11/shard/month) means even an idle stream costs more than an idle SQS queue
- Producers must implement batching and retry logic explicitly (handled in `clintrial.producer.kinesis_client`)
