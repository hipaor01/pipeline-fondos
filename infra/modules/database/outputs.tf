output "cluster_arn" {
  description = "ARN del clúster (resourceArn de la Data API)."
  value       = aws_rds_cluster.this.arn
}

output "cluster_identifier" {
  description = "Identificador del clúster."
  value       = aws_rds_cluster.this.cluster_identifier
}

output "secret_arn" {
  description = "ARN del secreto gestionado por RDS (secretArn de la Data API)."
  value       = aws_rds_cluster.this.master_user_secret[0].secret_arn
}

output "database_name" {
  description = "Nombre de la base de datos."
  value       = aws_rds_cluster.this.database_name
}

output "engine_version" {
  description = "Versión de Aurora PostgreSQL desplegada."
  value       = aws_rds_cluster.this.engine_version_actual
}
