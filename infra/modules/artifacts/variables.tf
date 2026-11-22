variable "bucket_name" {
  description = "Nombre globalmente único del bucket de artefactos."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name debe ser un nombre S3 válido de entre 3 y 63 caracteres, sin puntos."
  }
}

variable "project_name" {
  description = "Nombre del proyecto."
  type        = string
  default     = "pipeline-fondos"
}

variable "environment" {
  description = "Entorno al que pertenecen los artefactos."
  type        = string
}

variable "retention_days" {
  description = "Días durante los que se conservan los artefactos de dev."
  type        = number
  default     = 30

  validation {
    condition     = var.retention_days >= 1 && floor(var.retention_days) == var.retention_days
    error_message = "retention_days debe ser un número entero positivo."
  }
}

variable "additional_tags" {
  description = "Etiquetas adicionales del bucket."
  type        = map(string)
  default     = {}
}
