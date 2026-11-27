output "function_names" {
  description = "Funciones Lambda por etapa."
  value       = { for k, f in aws_lambda_function.this : k => f.function_name }
}

output "queue_urls" {
  description = "Colas de entrada por etapa."
  value       = { for k, q in aws_sqs_queue.this : k => q.url }
}

output "dlq_names" {
  description = "DLQ técnicas por etapa (para las alarmas de observabilidad de P3)."
  value       = { for k, q in aws_sqs_queue.dlq : k => q.name }
}

output "dlq_arns" {
  description = "ARN de las DLQ por etapa."
  value       = { for k, q in aws_sqs_queue.dlq : k => q.arn }
}

output "log_group_names" {
  description = "Grupos de logs por etapa."
  value       = { for k, g in aws_cloudwatch_log_group.lambda : k => g.name }
}

output "metrics_namespace" {
  description = "Espacio de nombres de las métricas EMF (Documentos y DuracionProceso por Etapa/Resultado)."
  value       = "PipelineFondos/Procesamiento"
}
