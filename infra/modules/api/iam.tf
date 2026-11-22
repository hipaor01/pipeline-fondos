data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    sid     = "AllowLambdaServiceToAssumeRole"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_execution" {
  name                 = local.lambda_execution_role_name
  description          = "Execution role for ${local.lambda_function_name}"
  assume_role_policy   = data.aws_iam_policy_document.lambda_assume_role.json
  permissions_boundary = var.lambda_permissions_boundary_arn

  tags = merge(
    local.common_tags,
    {
      Name = local.lambda_execution_role_name
    }
  )
}

data "aws_iam_policy_document" "lambda_logging" {
  statement {
    sid    = "WriteApplicationLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda_logging" {
  name   = "${local.lambda_function_name}-logs"
  role   = aws_iam_role.lambda_execution.id
  policy = data.aws_iam_policy_document.lambda_logging.json
}

# Los permisos para Aurora y Secrets Manager se añadirán cuando exista el
# repositorio correspondiente, limitándolos a sus ARN concretos.
