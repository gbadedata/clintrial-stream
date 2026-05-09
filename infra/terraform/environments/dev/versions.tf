# =============================================================================
# infra/terraform/environments/dev/versions.tf
# =============================================================================
# Pins Terraform CLI version and provider versions for reproducibility.
#
# Why pin? An unpinned configuration that runs today might break tomorrow when
# a new provider version is released. CI/CD agents need deterministic behaviour.
#
# Strategy:
#   - Terraform CLI: ">= 1.9, < 2.0" (allow patches, block major upgrade)
#   - AWS provider: ">= 5.50, < 6.0" (current major; tested syntax)
#   - Random provider: ">= 3.6, < 4.0" (used for unique suffixes)

terraform {
  required_version = ">= 1.9.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.50.0, < 6.0.0"
    }

    random = {
      source  = "hashicorp/random"
      version = ">= 3.6.0, < 4.0.0"
    }
  }
}
