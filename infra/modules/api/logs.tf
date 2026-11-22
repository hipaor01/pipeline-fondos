resource "aws_cloudwatch_log_group" "lambda" {
  name              = local.lambda_log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name    = local.lambda_log_group_name
      LogType = "application"
    }
  )
}

resource "aws_cloudwatch_log_group" "api_access" {
  name              = local.api_access_log_group_name
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name    = local.api_access_log_group_name
      LogType = "access"
    }
  )
}
