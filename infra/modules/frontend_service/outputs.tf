output "service_arn" {
  description = "ARN del servicio ECS Express del frontend."
  value       = aws_ecs_express_gateway_service.this.service_arn
}

output "service_revision_arn" {
  description = "ARN de la revisión desplegada del servicio."
  value       = aws_ecs_express_gateway_service.this.service_revision_arn
}

output "service_endpoint" {
  description = "Endpoint HTTPS público administrado por ECS Express."
  value = try(
    one([
      for path in aws_ecs_express_gateway_service.this.ingress_paths : path.endpoint
      if path.access_type == "PUBLIC"
    ]),
    null,
  )
}

output "log_group_name" {
  description = "Grupo de CloudWatch Logs del frontend."
  value       = aws_cloudwatch_log_group.frontend.name
}
