output "api_name" {
  description = "Nombre de la HTTP API."
  value       = aws_apigatewayv2_api.api.name
}

output "api_id" {
  description = "Identificador de la HTTP API."
  value       = aws_apigatewayv2_api.api.id
}

output "api_endpoint" {
  description = "URL base pública de la HTTP API con el stage por defecto."
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "api_execution_arn" {
  description = "Prefijo ARN de ejecución de la HTTP API."
  value       = aws_apigatewayv2_api.api.execution_arn
}

output "lambda_function_name" {
  description = "Nombre de la función Lambda de la API."
  value       = aws_lambda_function.api.function_name
}

output "lambda_function_arn" {
  description = "ARN de la función Lambda de la API."
  value       = aws_lambda_function.api.arn
}

output "lambda_invoke_arn" {
  description = "ARN de invocación que utilizará la integración de API Gateway."
  value       = aws_lambda_function.api.invoke_arn
}

output "lambda_execution_role_name" {
  description = "Nombre del rol de ejecución de Lambda."
  value       = aws_iam_role.lambda_execution.name
}

output "lambda_execution_role_arn" {
  description = "ARN del rol de ejecución de Lambda."
  value       = aws_iam_role.lambda_execution.arn
}

output "lambda_log_group_name" {
  description = "Nombre del grupo de logs de Lambda."
  value       = aws_cloudwatch_log_group.lambda.name
}

output "lambda_log_group_arn" {
  description = "ARN del grupo de logs de Lambda."
  value       = aws_cloudwatch_log_group.lambda.arn
}

output "api_access_log_group_name" {
  description = "Nombre del grupo de logs de acceso de API Gateway."
  value       = aws_cloudwatch_log_group.api_access.name
}

output "api_access_log_group_arn" {
  description = "ARN del grupo de logs de acceso de API Gateway."
  value       = aws_cloudwatch_log_group.api_access.arn
}

