variable "aws_region" {
  description = "Región de AWS en la que se crea el bucket del estado."
  type        = string
  default     = "eu-west-3"

  validation {
    condition     = can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region debe tener el formato de una región de AWS, por ejemplo eu-west-3."
  }
}

variable "project_name" {
  description = "Nombre corto del proyecto, utilizado para nombrar y etiquetar recursos."
  type        = string
  default     = "pipeline-fondos"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$", var.project_name))
    error_message = "project_name debe tener entre 3 y 30 caracteres: minúsculas, números y guiones."
  }
}

variable "state_bucket_name" {
  description = "Nombre opcional del bucket. Si se omite, se genera con el proyecto y el ID de la cuenta."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.state_bucket_name == null ||
      can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.state_bucket_name))
    )
    error_message = "state_bucket_name debe ser un nombre S3 válido de entre 3 y 63 caracteres, sin puntos."
  }
}

variable "artifact_bucket_name" {
  description = "Nombre previsto para el bucket de artefactos que creará la pipeline de CD."
  type        = string
  default     = null
  nullable    = true

  validation {
    condition = (
      var.artifact_bucket_name == null ||
      can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.artifact_bucket_name))
    )
    error_message = "artifact_bucket_name debe ser un nombre S3 válido de entre 3 y 63 caracteres, sin puntos."
  }
}

variable "deployment_environment" {
  description = "Entorno AWS que podrá desplegar el rol de GitHub Actions."
  type        = string
  default     = "dev"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,18}[a-z0-9]$|^[a-z0-9]$", var.deployment_environment))
    error_message = "deployment_environment debe tener entre 1 y 20 caracteres: minúsculas, números y guiones."
  }
}

variable "github_oidc_subject" {
  description = "Subject OIDC inmutable autorizado para asumir el rol de CD."
  type        = string
  default     = "repo:hipaor01@54775548/pipeline-fondos@1465066430:ref:refs/heads/main"

  validation {
    condition     = can(regex("^repo:[^:]+:ref:refs/heads/[A-Za-z0-9._/-]+$", var.github_oidc_subject))
    error_message = "github_oidc_subject debe identificar exactamente un repositorio y una rama."
  }
}

variable "additional_tags" {
  description = "Etiquetas adicionales que se aplican a los recursos del bootstrap."
  type        = map(string)
  default     = {}
}
