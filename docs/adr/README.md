# Architecture Decision Records

This directory holds the architectural decisions that shape ClinTrial-Stream. Each ADR captures one decision, the alternatives considered, and the reasoning, so future contributors (including future-me) can understand *why* the platform looks the way it does - not just *what* it is.

## Format

Each ADR follows a lightweight template:

- **Status** - Proposed, Accepted, Superseded
- **Context** - what problem we're solving
- **Decision** - what we chose
- **Alternatives** - what we rejected and why
- **Consequences** - tradeoffs we accept

## Index

| ID | Title | Status |
|---|---|---|
| [ADR-001](001-kinesis-over-sqs.md) | Kinesis Data Streams over SQS for ingestion | Accepted |
| [ADR-002](002-dynamodb-single-table.md) | DynamoDB single-table design | Accepted |
| [ADR-003](003-flask-over-fastapi.md) | Flask over FastAPI for the API layer | Accepted |
| [ADR-004](004-lambda-over-fargate.md) | Lambda over Fargate for the consumer | Accepted |
| [ADR-005](005-cognito-for-auth.md) | Cognito for OAuth2/JWT authentication | Accepted |
| [ADR-006](006-multi-cloud-portability.md) | Designed for AWS+GCP portability | Accepted |
