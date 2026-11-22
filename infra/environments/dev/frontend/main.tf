locals {
  environment     = "dev"
  repository_name = "${var.project_name}-${local.environment}-frontend"
}

module "container_registry" {
  source = "../../../modules/container_registry"

  repository_name      = local.repository_name
  project_name         = var.project_name
  environment          = local.environment
  retained_image_count = var.retained_image_count
  additional_tags      = var.additional_tags
}
