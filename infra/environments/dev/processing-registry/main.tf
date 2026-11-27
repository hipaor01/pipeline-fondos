# Repositorio ECR de la imagen de procesamiento (P2). Estado separado del root
# `processing` para poder publicar la imagen antes de crear las Lambdas que la usan.

locals {
  environment     = "dev"
  repository_name = "${var.project_name}-${local.environment}-processing"
}

module "container_registry" {
  source = "../../../modules/container_registry"

  repository_name      = local.repository_name
  project_name         = var.project_name
  environment          = local.environment
  component            = "processing"
  retained_image_count = var.retained_image_count
  additional_tags      = var.additional_tags
}

# Lambda descarga la imagen con su propio principal de servicio.
data "aws_iam_policy_document" "lambda_pull" {
  statement {
    sid     = "LambdaPullImage"
    effect  = "Allow"
    actions = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "aws:sourceArn"
      values   = ["arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-${local.environment}-*"]
    }
  }
}

data "aws_caller_identity" "current" {}

resource "aws_ecr_repository_policy" "lambda_pull" {
  repository = module.container_registry.repository_name
  policy     = data.aws_iam_policy_document.lambda_pull.json
}
