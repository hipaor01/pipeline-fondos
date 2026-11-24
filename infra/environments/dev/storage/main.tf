terraform {
  required_version = ">= 1.10.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0, < 7.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "eu-west-3"
}

variable "bucket_name" {
  description = "Nombre global del bucket de documentos."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name debe tener entre 3 y 63 caracteres, sin puntos y con formato S3 válido."
  }
}

variable "create_bucket" {
  description = "Crear y administrar un bucket nuevo; false solo referencia uno existente."
  type        = bool
  default     = false
}

resource "aws_s3_bucket" "documents" {
  count         = var.create_bucket ? 1 : 0
  bucket        = var.bucket_name
  force_destroy = false

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "documents" {
  count  = var.create_bucket ? 1 : 0
  bucket = aws_s3_bucket.documents[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  count  = var.create_bucket ? 1 : 0
  bucket = aws_s3_bucket.documents[0].id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  count                   = var.create_bucket ? 1 : 0
  bucket                  = aws_s3_bucket.documents[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "bucket_name" {
  value = var.bucket_name
}

output "bucket_arn" {
  value = "arn:${data.aws_partition.current.partition}:s3:::${var.bucket_name}"
}

data "aws_partition" "current" {}

output "bucket_region" {
  description = "Región configurada; comprobarla en AWS si el bucket ya existe."
  value       = var.aws_region
}
