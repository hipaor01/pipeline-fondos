# Capa de procesamiento y datos (P2) en dev: Aurora + colas + Lambdas.
# La imagen se publica antes en el root `processing-registry`.

data "aws_caller_identity" "current" {}

locals {
  environment = "dev"
  # Boundary creada en infra/bootstrap/processing_cd_permissions.tf
  permissions_boundary_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.project_name}-${local.environment}-processing-boundary"
}

module "database" {
  source = "../../../modules/database"

  project_name        = var.project_name
  environment         = local.environment
  database_name       = var.database_name
  max_capacity        = var.database_max_capacity
  deletion_protection = var.database_deletion_protection
  additional_tags     = var.additional_tags
}

module "processing" {
  source = "../../../modules/processing"

  project_name                = var.project_name
  environment                 = local.environment
  documents_bucket_name       = var.documents_bucket_name
  manage_bucket_notifications = var.manage_bucket_notifications
  image_uri                   = var.image_uri
  lambda_architecture         = var.lambda_architecture
  permissions_boundary_arn    = local.permissions_boundary_arn

  bedrock_model_id = var.bedrock_model_id

  database_cluster_arn = module.database.cluster_arn
  database_secret_arn  = module.database.secret_arn
  database_name        = module.database.database_name

  additional_tags = var.additional_tags
}
