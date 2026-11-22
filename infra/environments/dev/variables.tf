variable "aws_region" {
  description = "Región de AWS en la que se despliega la API."
  type        = string
  default     = "eu-west-3"

  validation {
    condition     = can(regex("^[a-z]{2}(-gov)?-[a-z]+-[0-9]+$", var.aws_region))
    error_message = "aws_region debe tener el formato de una región de AWS, por ejemplo eu-west-3."
  }
}

variable "project_name" {
  description = "Nombre corto del proyecto."
  type        = string
  default     = "pipeline-fondos"
}

variable "lambda_package" {
  description = "Artefacto ZIP de la API, construido para Linux y almacenado en S3."
  type = object({
    s3_bucket         = string
    s3_key            = string
    s3_object_version = optional(string)
    source_code_hash  = string
  })
}

variable "cors_allowed_origins" {
  description = "Orígenes permitidos por CORS. Una lista vacía desactiva CORS."
  type        = list(string)
  default     = ["http://localhost:3000"]

  validation {
    condition     = alltrue([for origin in var.cors_allowed_origins : length(trimspace(origin)) > 0])
    error_message = "cors_allowed_origins no puede contener valores vacíos."
  }
}

variable "lambda_environment_variables" {
  description = "Variables de entorno no sensibles de la aplicación."
  type        = map(string)
  default     = {}
}

variable "additional_tags" {
  description = "Etiquetas adicionales para los recursos de la API."
  type        = map(string)
  default     = {}
}
