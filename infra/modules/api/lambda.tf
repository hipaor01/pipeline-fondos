resource "aws_lambda_function" "api" {
  function_name = local.lambda_function_name
  description   = "FastAPI backend for ${var.project_name} (${var.environment})"
  role          = aws_iam_role.lambda_execution.arn

  package_type      = "Zip"
  s3_bucket         = var.lambda_package.s3_bucket
  s3_key            = var.lambda_package.s3_key
  s3_object_version = var.lambda_package.s3_object_version
  source_code_hash  = var.lambda_package.source_code_hash

  runtime       = var.lambda_runtime
  handler       = var.lambda_handler
  architectures = [var.lambda_architecture]
  memory_size   = var.lambda_memory_size
  timeout       = var.lambda_timeout_seconds

  environment {
    variables = var.lambda_environment_variables
  }

  tags = merge(
    local.common_tags,
    {
      Name = local.lambda_function_name
    }
  )

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda_logging,
  ]
}

