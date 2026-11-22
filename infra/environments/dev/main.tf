data "aws_caller_identity" "current" {}

locals {
  environment                     = "dev"
  lambda_permissions_boundary_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.project_name}-${local.environment}-lambda-boundary"
}

module "api" {
  source = "../../modules/api"

  project_name = var.project_name
  environment  = local.environment

  lambda_package                  = var.lambda_package
  lambda_environment_variables    = var.lambda_environment_variables
  lambda_permissions_boundary_arn = local.lambda_permissions_boundary_arn

  cors_configuration = length(var.cors_allowed_origins) == 0 ? null : {
    allow_origins = var.cors_allowed_origins
  }

  additional_tags = var.additional_tags
}
