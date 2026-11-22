data "aws_caller_identity" "current" {}

locals {
  environment          = "dev"
  artifact_bucket_name = "${var.project_name}-artifacts-${data.aws_caller_identity.current.account_id}"
}

module "artifacts" {
  source = "../../../modules/artifacts"

  bucket_name     = local.artifact_bucket_name
  project_name    = var.project_name
  environment     = local.environment
  retention_days  = var.artifact_retention_days
  additional_tags = var.additional_tags
}
