output "repository_name" {
  description = "Nombre del repositorio de la imagen de procesamiento."
  value       = module.container_registry.repository_name
}

output "repository_url" {
  description = "URL del repositorio utilizada por la pipeline."
  value       = module.container_registry.repository_url
}
