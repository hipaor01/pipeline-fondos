terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0, < 7.0"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "eu-west-3"
}

variable "project_name" {
  type    = string
  default = "pipeline-fondos"
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "lambda_pull" {
  statement {
    sid    = "LambdaECRImageRetrievalPolicy"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-dev-capture-*"]
    }
  }
}

module "registry" {
  source               = "../../../modules/container_registry"
  repository_name      = "${var.project_name}-dev-capture-scraper"
  project_name         = var.project_name
  environment          = "dev"
  component            = "capture"
  expirable_tag_prefix = "desechable-"
}

resource "aws_ecr_repository_policy" "lambda_pull" {
  repository = module.registry.repository_name
  policy     = data.aws_iam_policy_document.lambda_pull.json
}

output "repository_name" {
  value = module.registry.repository_name
}

output "repository_url" {
  value = module.registry.repository_url
}
