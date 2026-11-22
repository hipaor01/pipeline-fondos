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
