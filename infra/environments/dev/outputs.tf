output "api_endpoint" {
  description = "URL base de la API del entorno dev."
  value       = module.api.api_endpoint
}

output "health_url" {
  description = "URL del health check de la API."
  value       = "${module.api.api_endpoint}/health"
}

output "api_id" {
  description = "Identificador de API Gateway."
  value       = module.api.api_id
}

output "lambda_function_name" {
  description = "Nombre de la función Lambda desplegada."
  value       = module.api.lambda_function_name
}

output "lambda_log_group_name" {
  description = "Grupo de logs de la aplicación."
  value       = module.api.lambda_log_group_name
}

output "api_access_log_group_name" {
  description = "Grupo de access logs de API Gateway."
  value       = module.api.api_access_log_group_name
}
