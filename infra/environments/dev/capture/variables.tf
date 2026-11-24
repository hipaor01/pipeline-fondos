variable "aws_region" {
  type    = string
  default = "eu-west-3"
}

variable "project_name" {
  type    = string
  default = "pipeline-fondos"
}

variable "documents_bucket" {
  description = "Bucket de documentos existente, privado y versionado."
  type        = string
}

variable "image_uri" {
  description = "Imagen ECR de captura identificada por digest."
  type        = string
  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$", var.image_uri))
    error_message = "image_uri debe ser una imagen ECR identificada por digest."
  }
}

variable "schedule_enabled" {
  description = "Activa el horario diario una vez completadas las pruebas."
  type        = bool
  default     = false
}

variable "schedule_expression" {
  type    = string
  default = "cron(0 7 * * ? *)"
}
