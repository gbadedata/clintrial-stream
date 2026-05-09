# =============================================================================
# infra/terraform/environments/dev/providers.tf
# =============================================================================
# Configures the AWS provider with the region, profile, and default tags
# applied to every resource managed by this configuration.
#
# Default tags are powerful:
#   - Every resource automatically gets these tags (no need to repeat in each module)
#   - Cost allocation by Project, Environment, Component
#   - Audit trail showing what created each resource
#   - Easy filtering when querying AWS APIs

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project     = "clintrial-stream"
      Environment = var.environment
      ManagedBy   = "terraform"
      Owner       = "gbadedata"
      Repository  = "https://github.com/gbadedata/clintrial-stream"
    }
  }
}
