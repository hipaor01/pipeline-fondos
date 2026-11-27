variable "project_name" {
  description = "Nombre corto del proyecto."
  type        = string
  default     = "pipeline-fondos"
}

variable "environment" {
  description = "Entorno de despliegue (dev, prod...)."
  type        = string
}

variable "database_name" {
  description = "Nombre de la base de datos inicial."
  type        = string
  default     = "fondos"

  validation {
    condition     = can(regex("^[a-z][a-z0-9_]{0,62}$", var.database_name))
    error_message = "database_name debe empezar por letra y contener solo minúsculas, números y _."
  }
}

variable "master_username" {
  description = "Usuario maestro; su contraseña la gestiona RDS en Secrets Manager."
  type        = string
  default     = "fondos_admin"
}

variable "engine_major_version" {
  description = "Versión mayor de Aurora PostgreSQL; se usa la última menor disponible. 16.3+ admite 0 ACU."
  type        = string
  default     = "16"
}

variable "min_capacity" {
  description = "ACU mínimas. 0 permite pausar el clúster cuando no se usa."
  type        = number
  default     = 0
}

variable "max_capacity" {
  description = "ACU máximas."
  type        = number
  default     = 2

  validation {
    condition     = var.max_capacity >= 1 && var.max_capacity <= 256
    error_message = "max_capacity debe estar entre 1 y 256."
  }
}

variable "seconds_until_auto_pause" {
  description = "Segundos sin actividad antes de pausar (solo si min_capacity = 0)."
  type        = number
  default     = 900

  validation {
    condition     = var.seconds_until_auto_pause >= 300 && var.seconds_until_auto_pause <= 86400
    error_message = "seconds_until_auto_pause debe estar entre 300 y 86400."
  }
}

variable "backup_retention_days" {
  description = "Días de retención de copias automáticas."
  type        = number
  default     = 1
}

variable "deletion_protection" {
  description = "Impide borrar el clúster por error."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "No crear snapshot final al destruir (razonable en dev)."
  type        = bool
  default     = true
}

variable "additional_tags" {
  description = "Etiquetas adicionales."
  type        = map(string)
  default     = {}
}
