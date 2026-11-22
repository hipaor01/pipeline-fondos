resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/aws/ecs/${var.service_name}"
  retention_in_days = var.log_retention_days

  tags = merge(
    local.common_tags,
    {
      Name = "/aws/ecs/${var.service_name}"
    }
  )
}
