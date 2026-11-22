data "aws_caller_identity" "current" {}

locals {
  environment       = "dev"
  service_name      = "${var.project_name}-${local.environment}-frontend"
  state_bucket_name = "${var.project_name}-terraform-state-${data.aws_caller_identity.current.account_id}"
}

data "terraform_remote_state" "api" {
  backend = "s3"

  config = {
    bucket       = local.state_bucket_name
    key          = "${var.project_name}/${local.environment}/terraform.tfstate"
    region       = var.aws_region
    encrypt      = true
    use_lockfile = true
  }
}

module "frontend_service" {
  source = "../../../modules/frontend_service"

  service_name       = local.service_name
  container_image    = var.frontend_image
  api_base_url       = data.terraform_remote_state.api.outputs.api_endpoint
  cpu_units          = var.cpu_units
  memory_mib         = var.memory_mib
  min_task_count     = var.min_task_count
  max_task_count     = var.max_task_count
  log_retention_days = var.log_retention_days
  project_name       = var.project_name
  environment        = local.environment
  aws_region         = var.aws_region
  additional_tags    = var.additional_tags
}
