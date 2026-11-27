output "database_cluster_arn" {
  description = "ARN de Aurora para la Data API (la API de P3 lo necesita)."
  value       = module.database.cluster_arn
}

output "database_secret_arn" {
  description = "ARN del secreto de Aurora para la Data API (la API de P3 lo necesita)."
  value       = module.database.secret_arn
}

output "database_name" {
  description = "Base de datos."
  value       = module.database.database_name
}

output "function_names" {
  description = "Lambdas de procesamiento."
  value       = module.processing.function_names
}

output "dlq_names" {
  description = "DLQ técnicas para las alarmas."
  value       = module.processing.dlq_names
}

output "log_group_names" {
  description = "Grupos de logs."
  value       = module.processing.log_group_names
}
