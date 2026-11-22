output "repository_name" {
  description = "Nombre del repositorio del frontend."
  value       = module.container_registry.repository_name
}

output "repository_arn" {
  description = "ARN del repositorio del frontend."
  value       = module.container_registry.repository_arn
}

output "repository_url" {
  description = "URL del repositorio utilizada por la pipeline."
  value       = module.container_registry.repository_url
}
