output "state_bucket_name" {
  description = "Nombre del bucket S3 que almacenará los estados de Terraform."
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_arn" {
  description = "ARN del bucket S3 que almacenará los estados de Terraform."
  value       = aws_s3_bucket.terraform_state.arn
}

output "state_bucket_region" {
  description = "Región del bucket del estado."
  value       = var.aws_region
}

output "github_oidc_provider_arn" {
  description = "ARN del proveedor OIDC de GitHub Actions ya existente en la cuenta."
  value       = data.aws_iam_openid_connect_provider.github.arn
}

output "github_actions_cd_role_name" {
  description = "Nombre del rol que asumirá la pipeline de CD."
  value       = aws_iam_role.github_actions_cd.name
}

output "github_actions_cd_role_arn" {
  description = "ARN del rol que asumirá la pipeline de CD."
  value       = aws_iam_role.github_actions_cd.arn
}

output "github_oidc_subject" {
  description = "Subject OIDC exacto autorizado por la relación de confianza."
  value       = var.github_oidc_subject
}

output "artifact_bucket_name" {
  description = "Nombre reservado para el bucket de artefactos que creará la pipeline."
  value       = local.artifact_bucket_name
}

output "lambda_execution_permissions_boundary_arn" {
  description = "ARN de la frontera máxima de permisos para el rol de ejecución Lambda."
  value       = aws_iam_policy.lambda_execution_boundary.arn
}
