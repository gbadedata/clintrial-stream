# =============================================================================
# infra/terraform/environments/dev/backend.tf
# =============================================================================
# Configures Terraform to store its state remotely in S3 with DynamoDB locking.
#
# State management is one of the most important Terraform concepts:
#   - State tracks every resource Terraform manages
#   - Without a remote backend, state lives in `terraform.tfstate` on your laptop
#   - Local state means: lose laptop = lose ability to manage infrastructure
#   - It also means: two engineers can corrupt state by applying simultaneously
#
# Remote backend solves both:
#   - State stored in S3 (durable, versioned, encrypted)
#   - DynamoDB table provides locking — concurrent applies are serialised
#
# The bucket and DynamoDB table are created once by the bootstrap script,
# NOT by Terraform itself (chicken-and-egg problem).
#
# Each environment uses a different `key` so dev/staging/prod have isolated state.

terraform {
  backend "s3" {
    bucket       = "clintrial-stream-tfstate-677276115158"
    key          = "environments/dev/terraform.tfstate"
    region       = "eu-west-2"
    use_lockfile = true
    encrypt      = true
  }
}
