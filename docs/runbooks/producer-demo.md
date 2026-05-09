# Producer demo runbook

This runbook reproduces the live producer demo end-to-end. The platform must already be deployed (`terraform apply` completed in `infra/terraform/environments/dev/`).

## Prerequisites

- AWS CLI authenticated against an account where the platform is deployed
- `clintrial-admin` profile (or whatever IAM principal Terraform was run as)
- Live Kinesis stream `clintrial-stream-dev-events` in `eu-west-2`
- Local Python venv set up via `make setup` and `pip install -e .`

## Quick health check

Before running the producer, confirm the platform is up:

```bash
aws kinesis describe-stream-summary \
  --stream-name clintrial-stream-dev-events \
  --query 'StreamDescriptionSummary.{Name:StreamName,Status:StreamStatus,Shards:OpenShardCount}' \
  --output table
```

Expected: `Status=ACTIVE`, `Shards=2`.

## Run the producer

```bash
python -m clintrial.producer.cli --total 100 --rate 10 --console-logs
```

Flags:

| Flag | Default | Meaning |
|---|---|---|
| `--total` | from `settings.producer_total_events` | Events to emit (0 = forever) |
| `--rate` | from `settings.producer_rate_eps` | Events per second |
| `--batch-size` | 100 | Records per `PutRecords` call (max 500) |
| `--seed` | 42 | RNG seed — same seed produces identical events |
| `--n-patients` | 50 | Size of the synthetic patient pool |
| `--stream-name` | from settings | Override stream name for this run |
| `--json-logs / --console-logs` | `--json-logs` | Output format |

A 100-event run at 10 eps takes ~10 seconds. The producer prints a banner like:

```text
============================================================
 Producer run complete
============================================================
  Attempted:    100
  Succeeded:    100
  Failed:       0
  Batches sent: 1
  Duration:     10.1s
  Actual rate:  9.9 eps
============================================================
```

If `Failed > 0`, the producer exits non-zero (caught by CI / wrapper scripts). Look at `kinesis_partial_failure_will_retry` log lines for diagnostics — usually that means shard-level write throttling.

## Verify events landed

Read records back via the AWS CLI to prove the round-trip:

```bash
ITERATOR=$(aws kinesis get-shard-iterator \
  --stream-name clintrial-stream-dev-events \
  --shard-id shardId-000000000001 \
  --shard-iterator-type TRIM_HORIZON \
  --query 'ShardIterator' --output text)

aws kinesis get-records --shard-iterator "$ITERATOR" --limit 1 \
  --query 'Records[0].Data' --output text | base64 -d | python -m json.tool
```

You should see a real `AdverseEvent`, `LabResult`, or `EnrollmentEvent` — fully populated, ULID-keyed, ISO-8601 timestamps in UTC.

## CloudWatch metrics

The producer emits CloudWatch metrics via the [Embedded Metric Format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format_Specification.html). They appear in the `ClinTrialStream/Producer` namespace under dimensions `environment` and `stream_name`:

- `RecordsProduced` — events successfully written
- `RecordsFailed` — events lost after all retries
- `BatchLatencyMs` — wall-clock time per `PutRecords` call
- `BatchSize` — records per batch (useful to spot under-batching)

Pull them via the CLI:

```bash
aws cloudwatch get-metric-statistics \
  --namespace ClinTrialStream/Producer \
  --metric-name RecordsProduced \
  --dimensions Name=environment,Value=dev Name=stream_name,Value=clintrial-stream-dev-events \
  --start-time "$(date -u -d '15 minutes ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 60 \
  --statistics Sum \
  --region eu-west-2
```

## Tear down to stop the meter

End-of-session habit — costs nothing to recreate tomorrow:

```bash
cd infra/terraform/environments/dev
terraform destroy
```

The state backend (S3 + DynamoDB) survives because it's bootstrap-managed, not Terraform-managed. Re-applying tomorrow takes ~90 seconds.
