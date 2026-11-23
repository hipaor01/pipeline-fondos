# Un rol por Lambda, cada uno limitado a sus prefijos de S3, su cola y sus servicios.

locals {
  # Un perfil de inferencia (global./eu./us./apac.) enruta a varias regiones: hacen
  # falta permisos sobre el perfil y sobre el modelo base en esas regiones.
  bedrock_is_profile    = can(regex("^(global|eu|us|apac|jp|au)\\.", var.bedrock_model_id))
  bedrock_base_model_id = local.bedrock_is_profile ? join(".", slice(split(".", var.bedrock_model_id), 1, length(split(".", var.bedrock_model_id)))) : var.bedrock_model_id

  bedrock_resources = local.bedrock_is_profile ? [
    "arn:${local.partition}:bedrock:${local.region}:${local.account_id}:inference-profile/${var.bedrock_model_id}",
    "arn:${local.partition}:bedrock:*::foundation-model/${local.bedrock_base_model_id}",
    "arn:${local.partition}:bedrock:::foundation-model/${local.bedrock_base_model_id}",
    ] : [
    "arn:${local.partition}:bedrock:${local.region}::foundation-model/${var.bedrock_model_id}",
  ]

  s3_read_prefixes = {
    markdown   = ["raw/*", "processed/markdown/*"]
    extraccion = ["processed/markdown/*", "processed/structured/*"]
  }
  s3_write_prefixes = {
    markdown   = ["processed/markdown/*", "processed/structured/*"]
    extraccion = ["processed/structured/*"]
  }
  # Con ListBucket, HEAD de un objeto inexistente devuelve 404 y no 403.
  s3_list_prefixes = {
    markdown   = ["processed/markdown/*"]
    extraccion = ["processed/structured/*"]
  }
}

data "aws_iam_policy_document" "assume_lambda" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  for_each = local.stages

  name                 = "${each.value.function_name}-exec"
  description          = "Rol de ejecución de ${each.value.function_name}"
  assume_role_policy   = data.aws_iam_policy_document.assume_lambda.json
  permissions_boundary = var.permissions_boundary_arn

  tags = merge(local.common_tags, { Stage = each.key })
}

data "aws_iam_policy_document" "lambda" {
  for_each = local.stages

  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda[each.key].arn}:*"]
  }

  statement {
    sid = "ConsumeQueue"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [aws_sqs_queue.this[each.key].arn]
  }

  statement {
    sid       = "ReadDocuments"
    actions   = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = [for p in local.s3_read_prefixes[each.key] : "${local.bucket_arn}/${p}"]
  }

  statement {
    sid       = "WriteDocuments"
    actions   = ["s3:PutObject"]
    resources = [for p in local.s3_write_prefixes[each.key] : "${local.bucket_arn}/${p}"]
  }

  statement {
    sid       = "ListOwnPrefixes"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = local.s3_list_prefixes[each.key]
    }
  }

  dynamic "statement" {
    for_each = var.documents_bucket_kms_key_arn == null ? [] : [1]
    content {
      sid       = "UseBucketKey"
      actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
      resources = [var.documents_bucket_kms_key_arn]
    }
  }

  dynamic "statement" {
    for_each = each.key == "extraccion" ? [1] : []
    content {
      sid       = "InvokeBedrockModel"
      actions   = ["bedrock:InvokeModel"]
      resources = local.bedrock_resources
    }
  }

  dynamic "statement" {
    for_each = each.key == "extraccion" ? [1] : []
    content {
      sid = "UseDataApi"
      actions = [
        "rds-data:ExecuteStatement",
        "rds-data:BeginTransaction",
        "rds-data:CommitTransaction",
        "rds-data:RollbackTransaction",
      ]
      resources = [var.database_cluster_arn]
    }
  }

  dynamic "statement" {
    for_each = each.key == "extraccion" ? [1] : []
    content {
      sid       = "ReadDatabaseSecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.database_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "lambda" {
  for_each = local.stages

  name   = "${each.value.function_name}-policy"
  role   = aws_iam_role.lambda[each.key].id
  policy = data.aws_iam_policy_document.lambda[each.key].json
}
