data "aws_caller_identity" "current" {}

locals {
  state_bucket_name = coalesce(
    var.state_bucket_name,
    "${var.project_name}-terraform-state-${data.aws_caller_identity.current.account_id}"
  )

  artifact_bucket_name = coalesce(
    var.artifact_bucket_name,
    "${var.project_name}-artifacts-${data.aws_caller_identity.current.account_id}"
  )

  cd_role_name               = "${var.project_name}-${var.deployment_environment}-github-deploy"
  lambda_execution_role_name = "${var.project_name}-${var.deployment_environment}-api-exec"
  lambda_boundary_name       = "${var.project_name}-${var.deployment_environment}-lambda-boundary"

  common_tags = merge(
    var.additional_tags,
    {
      Project   = var.project_name
      ManagedBy = "Terraform"
    }
  )
}

resource "aws_s3_bucket" "terraform_state" {
  bucket        = local.state_bucket_name
  force_destroy = false

  tags = merge(
    local.common_tags,
    {
      Name    = local.state_bucket_name
      Purpose = "terraform-state"
    }
  )

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_ownership_controls" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "require_tls" {
  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    actions = ["s3:*"]

    resources = [
      aws_s3_bucket.terraform_state.arn,
      "${aws_s3_bucket.terraform_state.arn}/*",
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "require_tls" {
  bucket = aws_s3_bucket.terraform_state.id
  policy = data.aws_iam_policy_document.require_tls.json

  depends_on = [aws_s3_bucket_public_access_block.terraform_state]
}
