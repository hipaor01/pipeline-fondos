data "aws_caller_identity" "current" {}

locals {
  environment                     = "dev"
  lambda_permissions_boundary_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.project_name}-${local.environment}-lambda-boundary"
  state_bucket_name               = "${var.project_name}-terraform-state-${data.aws_caller_identity.current.account_id}"
}

data "terraform_remote_state" "processing" {
  backend = "s3"

  config = {
    bucket       = local.state_bucket_name
    key          = "${var.project_name}/${local.environment}/processing/terraform.tfstate"
    region       = var.aws_region
    encrypt      = true
    use_lockfile = true
  }
}

module "api" {
  source = "../../modules/api"

  project_name = var.project_name
  environment  = local.environment

  lambda_package                  = var.lambda_package
  lambda_environment_variables    = var.lambda_environment_variables
  lambda_permissions_boundary_arn = local.lambda_permissions_boundary_arn

  database_cluster_arn = data.terraform_remote_state.processing.outputs.database_cluster_arn
  database_secret_arn  = data.terraform_remote_state.processing.outputs.database_secret_arn
  database_name        = data.terraform_remote_state.processing.outputs.database_name

  cors_configuration = length(var.cors_allowed_origins) == 0 ? null : {
    allow_origins = var.cors_allowed_origins
  }

  additional_tags = var.additional_tags
}
