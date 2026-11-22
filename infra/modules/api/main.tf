locals {
  resource_prefix = "${var.project_name}-${var.environment}"

  api_name                   = "${local.resource_prefix}-http-api"
  lambda_function_name       = "${local.resource_prefix}-api"
  lambda_execution_role_name = "${local.lambda_function_name}-exec"
  lambda_log_group_name      = "/aws/lambda/${local.lambda_function_name}"
  api_access_log_group_name  = "/aws/apigateway/${local.api_name}"

  common_tags = merge(
    var.additional_tags,
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
      Component   = "api"
    }
  )
}
