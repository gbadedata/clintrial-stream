# ADR-006: Designed for AWS+GCP portability

**Status:** Accepted

## Context

Many regulated organisations adopt a multi-cloud posture to avoid vendor lock-in, satisfy data residency requirements that vary by region, or because acquisitions inherit infrastructure across providers. The architectural choices made for ClinTrial-Stream should not block a future migration of any one component to GCP.

This is *portability*, not *active multi-cloud deployment*. The platform deploys to AWS today; the design discipline ensures that swapping a component for its GCP equivalent is a refactor, not a rewrite.

## Decision

Adopt cloud-agnostic patterns wherever the cost is reasonable:

- **Terraform** for infrastructure (already cloud-agnostic) rather than CloudFormation
- **Domain layer** (Pydantic models) is pure Python with no AWS imports
- **Producer/consumer** code uses thin AWS SDK wrappers behind dependency-injected interfaces, so swapping `boto3.client("kinesis")` for the GCP Pub/Sub client is a constructor change, not a rewrite
- **Config** (Pydantic Settings) speaks env vars only, no AWS-specific secret retrieval at module-import time

Keep AWS-native where the cost of abstraction would dominate the benefit:

- **CloudWatch Logs / Metrics via EMF** is AWS-specific. The metrics protocol stays, but the consuming dashboard would change in GCP
- **IAM policies** in Terraform are AWS-specific by definition

## Equivalents

| AWS today | GCP equivalent | Code impact |
|---|---|---|
| Kinesis Data Streams | Pub/Sub | New thin client wrapper, same producer interface |
| DynamoDB | Firestore (Datastore mode) or Bigtable | New repository implementation, same domain interface |
| Lambda | Cloud Functions or Cloud Run | New deployment target, same handler code |
| S3 | Cloud Storage | New thin client wrapper |
| Cognito | Identity Platform / Firebase Auth | JWT verification logic adapts to a new JWKS endpoint |
| Athena | BigQuery | SQL is broadly compatible; partition syntax differs |
| CloudWatch | Cloud Monitoring + Cloud Logging | Switch the metrics emitter, dashboards rebuilt |

## Alternatives considered

**Full multi-cloud abstraction layer (e.g., a homegrown SDK that abstracts AWS and GCP)**

- Genuinely cloud-agnostic, but the abstraction layer becomes its own product
- Every new service requires a new abstraction, every change requires updating two backends
- Universally regretted in the systems that have tried it

**Pure AWS lock-in**

- Less code, faster delivery
- Acceptable when the organisation has bet definitively on one cloud
- Removes optionality at very low up-front cost - usually not the right tradeoff for a platform expected to live for years

## Consequences

**Positive**

- The team can credibly answer "what would it take to move this to GCP?" with a concrete refactor plan rather than "rewrite everything"
- Domain logic is testable without AWS credentials, which keeps the unit test suite fast and cheap to run
- New engineers can reason about the domain layer without learning AWS first

**Negative**

- Some boilerplate to wrap AWS SDK calls in interfaces that have only one implementation today
- Resists the temptation to use deeply AWS-native patterns (Step Functions, EventBridge Pipes) where they would be the simplest answer
- Discipline cost: every AWS-specific bit added needs a "do we accept this lock-in?" moment
