<div align="center">

# ClinTrial-Stream

**Real-time clinical trial event streaming platform on AWS**

A production-shaped data engineering project that ingests, processes, and queries adverse events, enrollment changes, and lab results from clinical trial sites — at sub-second latency, with regulatory-grade audit trails.

[![CI](https://github.com/gbadedata/clintrial-stream/actions/workflows/ci.yml/badge.svg)](https://github.com/gbadedata/clintrial-stream/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Code style: ruff](https://img.shields.io/badge/lint-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checker-mypy%20strict-2A6DB2.svg)](https://mypy-lang.org/)
[![Infrastructure: Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC.svg)](https://www.terraform.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Architecture](#architecture) ·
[Quickstart](#quickstart) ·
[Features](#features) ·
[ADRs](docs/adr/) ·
[Demo video](#demo)

</div>

---

## What this is

ClinTrial-Stream is a streaming data platform that simulates how a real biotech company processes telemetry from clinical trial sites worldwide. Trial sites emit events continuously — a patient enrolls, an adverse event is reported, lab results arrive. These events have to be:

1. **Ingested at scale** — thousands of events per second from hundreds of sites
2. **Processed in near-real-time** — adverse events of high severity must trigger safety alarms within seconds, not hours
3. **Queryable through an API** — trial coordinators need to look up patient state, recent events, and safety summaries on demand
4. **Preserved immutably** — every event must be archived for FDA audit (21 CFR Part 11 compliance)

This is a portfolio project, not a production system, but every architectural decision matches what a production system would do. It is structured to be cloned, deployed in 15 minutes, and torn down in 5. Cost while running: about £0.50 per day.

## Why I built this

I am applying for data engineering roles in Cambridge biotech. Job descriptions in the cluster (AstraZeneca, Illumina, Abcam, BenevolentAI, etc.) consistently ask for: streaming ingestion, AWS or GCP cloud-native architecture, Python, SQL, Flask/Django, container orchestration, Infrastructure as Code, and stakeholder-facing API design.

ClinTrial-Stream demonstrates all of those simultaneously, in the specific domain (clinical trials, regulatory data) where the work happens.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Trial site  │────▶│   Kinesis    │────▶│  Hot consumer    │──▶ DynamoDB
│   producer   │     │   (2 shards) │     │  (Lambda)        │   (state)
└──────────────┘     └──────┬───────┘     └──────────────────┘
                            │
                            ▼
                     ┌──────────────┐     ┌──────────────────┐
                     │   Firehose   │────▶│   S3 audit       │
                     │  (cold path) │     │   (immutable)    │
                     └──────────────┘     └──────────────────┘

                            ▲
                            │
┌──────────────┐     ┌──────┴───────┐     ┌──────────────────┐
│   Cognito    │────▶│  Flask API   │◀────│   DynamoDB       │
│  (JWT auth)  │     │  (read side) │     │   (queries)      │
└──────────────┘     └──────────────┘     └──────────────────┘
```

This is a **Lambda architecture** — the canonical streaming pattern with a hot path for real-time queries and a cold path for analytics and compliance. Used by every regulated industry that processes streaming data (finance, healthcare, pharma).

### Layer by layer

| Layer | Component | Purpose |
|---|---|---|
| **Ingestion** | Kinesis Data Streams | Buffers incoming events, enables fan-out to multiple consumers, provides 24-hour replay |
| **Hot processing** | AWS Lambda | Validates each event, updates patient state in DynamoDB, fires CloudWatch alarms on severe adverse events |
| **State store** | DynamoDB (single-table design) | Sub-10ms reads of current patient/study/event state, powering the API |
| **Cold path** | Kinesis Firehose → S3 | Immutable archive of every raw event for FDA audit (21 CFR Part 11) |
| **API** | Flask + Flask-RESTful | REST endpoints for trial coordinators, protected by Cognito JWT auth |
| **Auth** | AWS Cognito | OAuth2 client credentials flow, JWT token issuance and verification |
| **Observability** | CloudWatch (logs, metrics, alarms) + X-Ray | Structured JSON logs with correlation IDs across every service |
| **Infrastructure** | Terraform | All resources defined as code; reproducible in any AWS account in under 15 minutes |

See [`docs/architecture/`](docs/architecture/) for detailed diagrams and [`docs/adr/`](docs/adr/) for the reasoning behind each decision.

## Demo

A 3-minute video walkthrough is available [here](#) <!-- TODO: link demo video --> showing:

1. `terraform apply` provisioning the platform from scratch
2. The producer firing 1,000 synthetic adverse events into Kinesis
3. CloudWatch metrics updating in real-time
4. A safety alarm triggering on a "serious" severity event
5. The Flask API returning patient state and event history
6. `terraform destroy` cleaning up

## Quickstart

Tested on Ubuntu 24.04 (WSL2) with Python 3.12, Terraform 1.9+, AWS CLI v2, and Docker 28+.

### 1. Prerequisites

```bash
# Verify required tools
python3 --version       # 3.12+
terraform --version     # 1.9+
aws --version           # 2.x
docker --version        # 20+
make --version          # 4.x
```

### 2. Configure AWS

```bash
# Create a dedicated IAM user for this project (NEVER use root credentials)
# In the AWS Console: IAM > Users > Create user > Attach AdministratorAccess
# Generate access keys, then:

aws configure --profile clintrial
# AWS Access Key ID: AKIA...
# AWS Secret Access Key: ...
# Default region: eu-west-2
# Default output format: json

export AWS_PROFILE=clintrial
aws sts get-caller-identity   # verify
```

### 3. Clone and set up

```bash
git clone https://github.com/gbadedata/clintrial-stream.git
cd clintrial-stream

# Copy env template and fill in any blanks (Cognito IDs auto-populate after Terraform apply)
cp .env.example .env

# Create venv, install all deps, install pre-commit hooks
make setup
source .venv/bin/activate
```

### 4. Provision infrastructure

```bash
make tf-init    # one-time
make tf-plan    # see what will be created
make tf-apply   # confirm with 'yes'
```

This provisions: 1 Kinesis stream, 1 DynamoDB table, 2 S3 buckets, 1 Lambda function, 1 Cognito user pool, IAM roles, CloudWatch alarms. Total provisioning time: about 4 minutes.

### 5. Run the demo

```bash
# Terminal 1 — start the API
make api

# Terminal 2 — start the synthetic event producer
make producer EVENTS=1000 RATE=50

# Terminal 3 — query the API
curl http://localhost:8000/health
curl -H "Authorization: Bearer $(./scripts/get-token.sh)" http://localhost:8000/v1/patients
```

### 6. Tear down

```bash
make tf-destroy   # confirm with 'yes'
```

Verify the AWS account is clean:

```bash
make cost   # current month's spend by service
```

## Features

### Domain modeling

- **FDA E2B(R3) compliance** — adverse event records use the international ICH-E2B(R3) field standard required for regulatory submission
- **Pydantic v2 domain models** — every event validated at the boundary; malformed payloads rejected with structured errors
- **Surrogate keys + natural keys** — DynamoDB items use ULIDs internally, business identifiers (NCT numbers, patient IDs) preserved separately

### Streaming

- **Kinesis Data Streams** — 2 shards, 24-hour retention, deterministic partition keys by patient_id (preserves per-patient ordering)
- **Exponential backoff with jitter** — `tenacity`-based retry on every API call to AWS
- **Idempotent consumer** — re-processing the same event produces the same result; safe to replay from any point in the 24h window
- **Dead letter queue** — events that fail validation 3 times are routed to a quarantine S3 prefix with their rejection reason

### API

- **Flask + Flask-RESTful** — chosen specifically over FastAPI to demonstrate familiarity with the dominant Python web framework in regulated industries
- **OpenAPI 3 spec** — auto-generated from Flask route metadata, served at `/openapi.json`
- **Pagination on every list endpoint** — `limit`/`offset` query parameters with sensible defaults
- **JWT auth via Cognito** — bearer tokens verified using the JWKS endpoint
- **CORS configured** — allows browser access from configurable origins
- **Health endpoints** — `/health` for liveness, `/health/ready` for readiness (checks DynamoDB connectivity)

### Observability

- **Structured JSON logs** — every log line is queryable in CloudWatch Logs Insights
- **Correlation IDs** — a single UUID traces an event from producer → Kinesis → consumer → DynamoDB → API
- **Custom CloudWatch metrics** — events processed, validation failures, safety alarm triggers, API error rate
- **CloudWatch alarms** — quarantine rate above 5%, API error rate above 1%, all wired to SNS

### Infrastructure

- **100% Terraform** — every AWS resource defined as code; no Console clicks required
- **Modular Terraform layout** — reusable modules in `infra/terraform/modules/`, environments wired in `infra/terraform/environments/`
- **Remote state backend** — Terraform state stored in S3 with DynamoDB locking
- **Least-privilege IAM** — every IAM role has only the specific permissions it needs

### Quality engineering

- **Pre-commit hooks** — ruff, mypy, detect-secrets, gitleaks, terraform fmt, markdownlint, shellcheck all run before every commit
- **GitHub Actions CI** — runs lint, type-check, tests on every push; deploys on merge to `main`
- **Strict mypy** — `strict = true` everywhere; no untyped code in production paths
- **70% coverage minimum** — CI fails if test coverage drops below threshold
- **Conventional commits** — commit messages enforced via pre-commit hook

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| **Language** | Python 3.12 | Universal in data eng; matches AWS Lambda's stable runtime |
| **Web framework** | Flask + Flask-RESTful | JD requirement; mature, simple, well-understood in regulated industries |
| **Validation** | Pydantic v2 | De facto standard for Python data validation; integrates with Flask via blueprints |
| **AWS SDK** | boto3 + botocore | Official Python SDK; auto-typed via boto3-stubs |
| **Streaming** | AWS Kinesis | Native AWS streaming; fan-out via enhanced consumers; replay window |
| **State store** | DynamoDB (on-demand pricing) | Sub-10ms reads at any scale; pay-per-request fits irregular demo workloads |
| **Auth** | AWS Cognito | OAuth2/OIDC compliant; JWT issuance; serverless |
| **Observability** | CloudWatch Logs/Metrics/Alarms + X-Ray | Native AWS; no extra setup or cost |
| **IaC** | Terraform 1.9 | Cloud-agnostic, declarative, mature |
| **Container** | Docker (multi-stage build) | Standard packaging for the Flask API |
| **Linter / formatter** | Ruff | 100x faster than flake8/black/isort; replaces all three |
| **Type checker** | mypy (strict mode) | Catches type errors at lint time |
| **Test runner** | pytest + moto + pytest-cov | Industry standard; moto fakes AWS services in unit tests |
| **CI/CD** | GitHub Actions | Free for public repos; mature ecosystem |

## Project structure

```
clintrial-stream/
├── .github/                    # GitHub Actions, issue templates
│   └── workflows/
├── docs/                       # Architecture, ADRs, runbooks
│   ├── architecture/           # System diagrams + prose
│   ├── adr/                    # Architecture Decision Records
│   └── runbooks/               # Operational guides (deploy, recover, etc.)
├── infra/
│   └── terraform/
│       ├── modules/            # Reusable: kinesis, dynamodb, cognito, etc.
│       └── environments/
│           └── dev/            # Wires modules together for dev environment
├── src/
│   └── clintrial/              # Application code (src/ layout)
│       ├── api/                # Flask app, routes, middleware
│       ├── auth/               # Cognito JWT verification
│       ├── consumer/           # Lambda code processing Kinesis events
│       ├── domain/             # Pydantic models, FDA E2B(R3) validation
│       ├── observability/      # Structured logging, metrics, tracing
│       ├── persistence/        # DynamoDB single-table design, repositories
│       └── producer/           # Synthetic event generator (demo)
├── tests/
│   ├── unit/                   # Pure logic, no AWS, no network
│   ├── integration/            # Against moto / LocalStack
│   └── fixtures/               # Sample events, test data
├── scripts/                    # One-off scripts (demo, load test)
├── assets/
│   ├── diagrams/               # Architecture diagrams (PNG/SVG)
│   └── screenshots/            # Console screenshots for README
├── .editorconfig               # Cross-editor format consistency
├── .env.example                # Environment variables template
├── .gitignore                  # Excludes secrets, build artifacts, etc.
├── .pre-commit-config.yaml     # Pre-commit hooks
├── .python-version             # Locked to 3.12
├── Makefile                    # Single source of truth for project commands
├── pyproject.toml              # Python config (deps, ruff, mypy, pytest)
└── README.md                   # This file
```

## Development

```bash
make help            # show all available commands
make setup           # create venv, install deps, install pre-commit hooks
make fmt             # format code with ruff
make lint            # run ruff linter
make typecheck       # run mypy strict
make test            # run all tests with coverage
make test-unit       # only unit tests
make test-integration # only integration tests (requires AWS or LocalStack)
make pre-commit      # run all pre-commit hooks against every file
make ci              # run lint + typecheck + test (same as GitHub Actions)
make cost            # current month AWS costs by service
```

### Adding a new feature

1. Branch off `main`: `git checkout -b feat/your-feature`
2. Write failing tests first (`tests/unit/...`)
3. Implement the feature in `src/clintrial/...`
4. Run `make ci` until green
5. Commit using [Conventional Commits](https://www.conventionalcommits.org/) format: `feat(api): add /patients/{id}/events endpoint`
6. Open a PR against `main`

### Pre-commit hooks

The first commit after `make setup` triggers all pre-commit hooks. Subsequent commits run them on changed files only. To bypass (rare; only when working in WIP branches):

```bash
git commit --no-verify -m "wip: incomplete refactor"
```

## Deployment

For now, deployment is manual via `make tf-apply`. Phase 2 of this project adds:

- GitHub Actions deploy workflow on merge to `main`
- Blue/green Lambda deployment using AWS CodeDeploy
- Automated rollback on CloudWatch alarm trigger

## Cost

Estimated AWS cost while running, in eu-west-2:

| Resource | Monthly cost |
|---|---|
| Kinesis Data Streams (2 shards, 24h retention) | $22.50 |
| Lambda (1M invocations, 128 MB) | $0.20 |
| DynamoDB (on-demand, ~10k requests) | $0.50 |
| S3 (audit bucket, ~1 GB) | $0.03 |
| CloudWatch Logs (7-day retention) | $0.50 |
| Cognito (50,000 free MAU) | $0.00 |
| **Total (running 24/7)** | **~$24/month** |
| **Total (typical demo: 2 hours)** | **~$0.07** |

The platform is **designed to be torn down between demos**. `make tf-destroy` removes everything in 5 minutes. The CloudWatch billing alarm at $10/month catches any forgotten resources within 6 hours.

See [`make cost`](Makefile) for live cost reporting.

## Architecture decision records

Each ADR documents a single architectural decision, the alternatives considered, and the reasoning. Read them when you want to understand *why* the platform looks the way it does.

| ID | Title |
|---|---|
| [ADR-001](docs/adr/001-kinesis-over-sqs.md) | Why Kinesis Data Streams over SQS |
| [ADR-002](docs/adr/002-dynamodb-single-table.md) | DynamoDB single-table design |
| [ADR-003](docs/adr/003-flask-over-fastapi.md) | Flask over FastAPI for this project |
| [ADR-004](docs/adr/004-lambda-over-fargate.md) | Lambda over Fargate for the consumer |
| [ADR-005](docs/adr/005-cognito-for-auth.md) | Cognito for OAuth2/JWT auth |
| [ADR-006](docs/adr/006-multi-cloud-portability.md) | Designed for AWS+GCP portability |

## Background

This is **Project 1 of 3** in a larger biotech-data-engineering portfolio:

1. **ClinTrial-Stream** *(this repo)* — Real-time clinical trial events on AWS (Kinesis, DynamoDB, Flask, Cognito)
2. **GenomeVault** — Genomic variant warehouse on GCP (BigQuery, Dataflow, Django, Looker)
3. **BioAuth-Mesh** — Multi-cloud platform with Kubernetes service mesh and OIDC federation

Together they cover every requirement of a senior data engineer JD in Cambridge biotech: streaming, batch, NoSQL, SQL, BigQuery, AWS, GCP, Python, Flask, Django, Terraform, Docker, Kubernetes, OAuth/OIDC, and bioinformatics domain depth.

## Author

**Gbade Odimayo**
Data Engineer · Cambridge UK
[gbadedata.com](https://gbadedata.com) · [GitHub](https://github.com/gbadedata) · [LinkedIn](https://linkedin.com/in/gbadedata)

## License

[MIT](LICENSE) — use, modify, and distribute freely. If you find it useful, a star on GitHub is appreciated.
