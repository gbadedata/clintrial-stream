# ADR-002: DynamoDB single-table design

**Status:** Accepted

## Context

The hot-path data store needs to support sub-10ms reads keyed by patient, study, or event ID, scale automatically as the trial onboards more sites, and accept variable-shape items (adverse events, enrollment events, and lab results have different fields).

A relational database (RDS, Aurora) would model this with one table per entity type and joins. DynamoDB's design philosophy - and the one championed by the AWS database team - is that all access patterns for a single application should usually fit in one table.

## Decision

Use a **single DynamoDB table** with a generic primary key (`PK`, `SK`) and item-type-specific attributes.

Access pattern catalogue:

| Pattern | PK | SK |
|---|---|---|
| Get patient profile | `PATIENT#<patient_id>` | `PROFILE` |
| List events for a patient (newest first) | `PATIENT#<patient_id>` | `EVENT#<reverse_iso_timestamp>#<event_id>` |
| Get a specific event | `EVENT#<event_id>` | `EVENT#<event_id>` |
| List events for a study | `STUDY#<study_id>` | `EVENT#<reverse_iso_timestamp>#<event_id>` |

## Alternatives considered

**One table per entity type (multi-table)**

- Closer to relational habits, simpler at first
- Forces multiple round-trips per request (get patient + get events = two `Query` calls)
- Each table has its own capacity allocation, more cost overhead
- Joins must happen application-side anyway - no win

**RDS PostgreSQL**

- Familiar SQL, joins, transactions across tables
- Sub-10ms reads achievable but with more operational overhead (VPC, parameter groups, failover)
- Vertical scaling ceiling - sharding becomes a project of its own
- Considered but rejected because the access patterns are key-based, not analytical

**Aurora Serverless v2**

- DynamoDB-like scaling for relational workloads
- Cold-start latency under low traffic (acceptable for batch, not for an interactive API)
- Higher minimum cost than DynamoDB at low usage

## Consequences

**Positive**

- One `Query` per access pattern - no joins, no N+1
- Pay-per-request billing means an idle environment costs nothing
- Adding a new access pattern usually means a new GSI, not a schema migration

**Negative**

- The schema is implicit - application code is the source of truth for what `PK` and `SK` mean for each item
- Aggregation queries ("how many adverse events this week across all studies") are awkward - those go to Athena over the S3 cold path, not DynamoDB
- Onboarding a new engineer to single-table design takes deliberate explanation - it is genuinely counterintuitive coming from a relational background
