resource "aws_apigatewayv2_api" "api" {
  name          = local.api_name
  description   = "HTTP API for ${var.project_name} (${var.environment})"
  protocol_type = "HTTP"

  dynamic "cors_configuration" {
    for_each = var.cors_configuration == null ? [] : [var.cors_configuration]

    content {
      allow_origins     = cors_configuration.value.allow_origins
      allow_methods     = cors_configuration.value.allow_methods
      allow_headers     = cors_configuration.value.allow_headers
      expose_headers    = cors_configuration.value.expose_headers
      allow_credentials = cors_configuration.value.allow_credentials
      max_age           = cors_configuration.value.max_age_seconds
    }
  }

  tags = merge(
    local.common_tags,
    {
      Name = local.api_name
    }
  )
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id = aws_apigatewayv2_api.api.id

  description            = "Lambda proxy integration for ${local.lambda_function_name}"
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "default" {
  api_id = aws_apigatewayv2_api.api.id

  route_key          = "$default"
  authorization_type = "NONE"
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id = aws_apigatewayv2_api.api.id

  name        = "$default"
  auto_deploy = true

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_access.arn
    format = jsonencode({
      requestId               = "$context.requestId"
      lambdaRequestId         = "$context.awsEndpointRequestId"
      sourceIp                = "$context.identity.sourceIp"
      userAgent               = "$context.identity.userAgent"
      requestTime             = "$context.requestTime"
      httpMethod              = "$context.httpMethod"
      path                    = "$context.path"
      routeKey                = "$context.routeKey"
      status                  = "$context.status"
      protocol                = "$context.protocol"
      responseLength          = "$context.responseLength"
      responseLatency         = "$context.responseLatency"
      integrationStatus       = "$context.integrationStatus"
      integrationLatency      = "$context.integrationLatency"
      integrationErrorMessage = "$context.integrationErrorMessage"
    })
  }

  default_route_settings {
    throttling_burst_limit = var.throttling.burst_limit
    throttling_rate_limit  = var.throttling.rate_limit
  }

  tags = merge(
    local.common_tags,
    {
      Name = "${local.api_name}-default-stage"
    }
  )

  depends_on = [aws_apigatewayv2_route.default]
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowInvocationFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*"
}
