data "aws_iam_policy_document" "lambda_execution_boundary" {
  statement {
    sid    = "WriteApplicationLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.deployment_environment}-api:*",
    ]
  }

  statement {
    sid       = "QueryAuroraDataApi"
    effect    = "Allow"
    actions   = ["rds-data:ExecuteStatement"]
    resources = [local.processing_cluster_arn]
  }

  # El ARN exacto lo restringe la política del rol de la Lambda. La boundary se
  # crea antes que Aurora y por eso admite cualquier secreto gestionado por RDS.
  statement {
    sid       = "ReadAuroraCredentials"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.processing_secret_arn]
  }
}

resource "aws_iam_policy" "lambda_execution_boundary" {
  name        = local.lambda_boundary_name
  description = "Maximum permissions for the ${var.project_name} ${var.deployment_environment} API Lambda role"
  policy      = data.aws_iam_policy_document.lambda_execution_boundary.json

  tags = merge(
    local.common_tags,
    {
      Name        = local.lambda_boundary_name
      Environment = var.deployment_environment
      Purpose     = "permissions-boundary"
    }
  )
}
