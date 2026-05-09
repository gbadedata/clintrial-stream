# Terraform infrastructure

All infrastructure for ClinTrial-Stream is defined here as code. Nothing is provisioned by clicking around the AWS Console.

## Layout

```
infra/terraform/
├── modules/              Reusable infrastructure components
│   ├── kinesis-stream/   (added in Step 5.1)
│   ├── dynamodb-table/   (added in Step 5.2)
│   ├── s3-audit-bucket/  (added in Step 5.3)
│   ├── lambda-consumer/  (added in Step 5.4)
│   └── cognito/          (added in Step 5.5)
└── environments/         Per-environment compositions
    ├── dev/              The dev environment (active)
    ├── staging/          (future)
    └── prod/             (future)
```

## Module / environment split

**Modules are reusable, environments are concrete.** A module like `kinesis-stream` declares "I create a Kinesis stream with these inputs and produce these outputs." The dev environment imports that module and says "use 2 shards, name it `clintrial-stream-events-dev`."

This split lets us roll out the same infrastructure to multiple environments by changing only the `terraform.tfvars` file, never the module source code.

## State backend

Terraform state lives in S3 (`clintrial-stream-tfstate-677276115158`) with DynamoDB locking (`clintrial-stream-tflock`). The backend was bootstrapped once via `scripts/bootstrap-terraform-backend.sh` before the first `terraform init` ran.

State is never committed to git. The `.gitignore` blocks `*.tfstate` and `.terraform/`.

## Workflow

```bash
# From the repo root
make tf-init       # one-time per environment
make tf-plan       # dry-run, see what would change
make tf-apply      # apply changes (asks for confirmation)
make tf-destroy    # tear down everything (asks for "yes" confirmation)
```

Or directly:

```bash
cd infra/terraform/environments/dev
terraform init
terraform plan
terraform apply
```

## Cost

Estimates for the dev environment running 24/7 in eu-west-2:

| Resource | Monthly cost |
|---|---|
| Kinesis Data Streams (2 shards, 24h retention) | $22.50 |
| DynamoDB (PAY_PER_REQUEST, low traffic) | $0.50 |
| S3 audit bucket (~1 GB) | $0.03 |
| Lambda (when added) | $0.20 |
| **Total** | **~$23-25/month** |

For demos: provision, run for an hour, destroy. That costs about $0.07 per session.

## When to add a new resource

1. Decide if it's a new component (module) or a tweak to an existing one
2. If new module: create `infra/terraform/modules/<name>/` with `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, `README.md`
3. Wire it into the environment by adding a `module "x"` block in `environments/dev/main.tf`
4. Add corresponding variables to `environments/dev/variables.tf` and values to `terraform.tfvars`
5. `make tf-plan` then `make tf-apply`
6. Update this README's module list

## Conventions

| Aspect | Convention |
|---|---|
| Naming | `${project}-${component}-${environment}` (e.g. `clintrial-stream-events-dev`) |
| Tags | `Project`, `Environment`, `Component`, `ManagedBy`, `Owner` (default tags via provider) |
| File names | `main.tf`, `variables.tf`, `outputs.tf`, `versions.tf` (consistent across modules) |
| Indentation | 2 spaces (Terraform community convention) |
| Variable validation | Every input variable should have a `validation` block |
| Module documentation | Every module has a `README.md` describing inputs, outputs, and usage |
