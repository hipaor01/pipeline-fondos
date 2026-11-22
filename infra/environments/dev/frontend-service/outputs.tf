output "service_arn" {
  description = "ARN del servicio ECS Express."
  value       = module.frontend_service.service_arn
}

output "service_revision_arn" {
  description = "ARN de la revisión actualmente desplegada."
  value       = module.frontend_service.service_revision_arn
}

output "service_endpoint" {
  description = "Endpoint HTTPS público del frontend."
  value       = module.frontend_service.service_endpoint
}

output "health_url" {
  description = "URL pública de salud de Streamlit."
  value = module.frontend_service.service_endpoint == null ? null : (
    "${trimsuffix(module.frontend_service.service_endpoint, "/")}/_stcore/health"
  )
}

output "log_group_name" {
  description = "Grupo de CloudWatch Logs de Streamlit."
  value       = module.frontend_service.log_group_name
}
