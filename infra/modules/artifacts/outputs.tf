output "bucket_name" {
  description = "Nombre del bucket de artefactos."
  value       = aws_s3_bucket.artifacts.id
}

output "bucket_arn" {
  description = "ARN del bucket de artefactos."
  value       = aws_s3_bucket.artifacts.arn
}
