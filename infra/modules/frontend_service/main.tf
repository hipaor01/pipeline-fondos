locals {
  common_tags = merge(
    var.additional_tags,
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
      Component   = "frontend"
    }
  )
}

resource "aws_ecs_express_gateway_service" "this" {
  service_name            = var.service_name
  cluster                 = "default"
  execution_role_arn      = aws_iam_role.task_execution.arn
  infrastructure_role_arn = aws_iam_role.infrastructure.arn
  cpu                     = tostring(var.cpu_units)
  memory                  = tostring(var.memory_mib)
  cpu_architecture        = "ARM64"
  health_check_path       = var.health_check_path
  wait_for_steady_state   = true

  primary_container {
    image          = var.container_image
    container_port = var.container_port

    aws_logs_configuration {
      log_group         = aws_cloudwatch_log_group.frontend.name
      log_stream_prefix = "streamlit"
    }

    environment {
      name  = "API_BASE_URL"
      value = var.api_base_url
    }

    environment {
      name  = "API_TIMEOUT_SECONDS"
      value = tostring(var.api_timeout_seconds)
    }
  }

  scaling_target {
    min_task_count            = var.min_task_count
    max_task_count            = var.max_task_count
    auto_scaling_metric       = "AVERAGE_CPU"
    auto_scaling_target_value = 60
  }

  tags = local.common_tags

  depends_on = [
    time_sleep.iam_propagation,
  ]

  lifecycle {
    precondition {
      condition = (
        (var.cpu_units == 256 && contains([512, 1024, 2048], var.memory_mib)) ||
        (var.cpu_units == 512 && contains([1024, 2048, 3072, 4096], var.memory_mib)) ||
        (var.cpu_units == 1024 && var.memory_mib >= 2048 && var.memory_mib <= 8192)
      )
      error_message = "La combinación de CPU y memoria debe ser válida para Fargate y no superar 1 vCPU."
    }

    precondition {
      condition     = var.min_task_count <= var.max_task_count
      error_message = "min_task_count no puede ser mayor que max_task_count."
    }
  }

  timeouts {
    create = "30m"
    update = "30m"
    delete = "20m"
  }
}
