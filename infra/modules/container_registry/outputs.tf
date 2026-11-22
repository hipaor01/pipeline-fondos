output "repository_name" {
  description = "Nombre del repositorio de ECR."
  value       = aws_ecr_repository.this.name
}

output "repository_arn" {
  description = "ARN del repositorio de ECR."
  value       = aws_ecr_repository.this.arn
}

output "repository_url" {
  description = "URL utilizada para publicar y descargar imágenes."
  value       = aws_ecr_repository.this.repository_url
}
