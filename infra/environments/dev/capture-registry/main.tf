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

module "registry" {
  source          = "../../../modules/container_registry"
  repository_name = "${var.project_name}-dev-capture-scraper"
  project_name    = var.project_name
  environment     = "dev"
  component       = "capture"
}

output "repository_url" {
  value = module.registry.repository_url
}
