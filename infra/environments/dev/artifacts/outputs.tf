output "artifact_bucket_name" {
  description = "Nombre del bucket al que la pipeline sube los ZIP."
  value       = module.artifacts.bucket_name
}

output "artifact_bucket_arn" {
  description = "ARN del bucket de artefactos."
  value       = module.artifacts.bucket_arn
}
