variable "project_name" {
  description = "Nombre corto del proyecto, utilizado para nombrar y etiquetar recursos."
  type        = string
  default     = "pipeline-fondos"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$", var.project_name))
    error_message = "project_name debe tener entre 3 y 30 caracteres: minúsculas, números y guiones."
  }
}

variable "environment" {
  description = "Nombre del entorno de despliegue, por ejemplo dev, staging o prod."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,18}[a-z0-9]$|^[a-z0-9]$", var.environment))
    error_message = "environment debe tener entre 1 y 20 caracteres: minúsculas, números y guiones."
  }
}

variable "lambda_package" {
  description = "Artefacto ZIP inmutable, construido para Linux y almacenado en S3."
  type = object({
    s3_bucket         = string
    s3_key            = string
    s3_object_version = optional(string)
    source_code_hash  = string
  })

  validation {
    condition = (
      length(trimspace(var.lambda_package.s3_bucket)) > 0 &&
      length(trimspace(var.lambda_package.s3_key)) > 0 &&
      (var.lambda_package.s3_object_version == null ? true : length(trimspace(var.lambda_package.s3_object_version)) > 0) &&
      can(regex("^[A-Za-z0-9+/]{43}=$", var.lambda_package.source_code_hash))
    )
    error_message = "lambda_package requiere bucket y key no vacíos, y source_code_hash en Base64 SHA-256."
  }
}

variable "lambda_runtime" {
  description = "Runtime administrado utilizado por la función Lambda."
  type        = string
  default     = "python3.14"

  validation {
    condition     = can(regex("^python3\\.[0-9]+$", var.lambda_runtime))
    error_message = "lambda_runtime debe ser un runtime Python, por ejemplo python3.14."
  }
}

variable "lambda_handler" {
  description = "Handler Python que invoca AWS Lambda."
  type        = string
  default     = "api.lambda_handler.handler"

  validation {
    condition     = can(regex("^[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z_][A-Za-z0-9_]*)+$", var.lambda_handler))
    error_message = "lambda_handler debe ser una ruta Python válida, por ejemplo api.lambda_handler.handler."
  }
}

variable "lambda_architecture" {
  description = "Arquitectura de CPU de la función Lambda."
  type        = string
  default     = "x86_64"

  validation {
    condition     = contains(["x86_64", "arm64"], var.lambda_architecture)
    error_message = "lambda_architecture debe ser x86_64 o arm64."
  }
}

variable "lambda_memory_size" {
  description = "Memoria asignada a Lambda, en MB."
  type        = number
  default     = 512

  validation {
    condition = (
      var.lambda_memory_size >= 128 &&
      var.lambda_memory_size <= 10240 &&
      floor(var.lambda_memory_size) == var.lambda_memory_size
    )
    error_message = "lambda_memory_size debe ser un número entero entre 128 y 10240 MB."
  }
}

variable "lambda_timeout_seconds" {
  description = "Tiempo máximo de una invocación de Lambda, en segundos."
  type        = number
  default     = 15

  validation {
    condition = (
      var.lambda_timeout_seconds >= 1 &&
      var.lambda_timeout_seconds <= 900 &&
      floor(var.lambda_timeout_seconds) == var.lambda_timeout_seconds
    )
    error_message = "lambda_timeout_seconds debe ser un número entero entre 1 y 900."
  }
}

variable "lambda_environment_variables" {
  description = "Variables de entorno no sensibles que recibe la aplicación."
  type        = map(string)
  default     = {}
}

variable "lambda_permissions_boundary_arn" {
  description = "ARN de la permissions boundary obligatoria para el rol de ejecución Lambda."
  type        = string

  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:policy/[A-Za-z0-9+=,.@_-]+$", var.lambda_permissions_boundary_arn))
    error_message = "lambda_permissions_boundary_arn debe ser el ARN de una política IAM."
  }
}

variable "log_retention_days" {
  description = "Retención de los logs de Lambda y de acceso de API Gateway."
  type        = number
  default     = 30

  validation {
    condition = contains([
      1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545,
      731, 1096, 1827, 2192, 2557, 2922, 3288, 3653,
    ], var.log_retention_days)
    error_message = "log_retention_days debe ser uno de los periodos admitidos por CloudWatch Logs."
  }
}

variable "cors_configuration" {
  description = "Configuración CORS de HTTP API. Un valor null mantiene CORS desactivado."
  type = object({
    allow_origins     = list(string)
    allow_methods     = optional(list(string), ["GET", "OPTIONS"])
    allow_headers     = optional(list(string), ["Content-Type", "X-Correlation-ID"])
    expose_headers    = optional(list(string), ["X-Correlation-ID"])
    allow_credentials = optional(bool, false)
    max_age_seconds   = optional(number, 300)
  })
  default  = null
  nullable = true

  validation {
    condition = var.cors_configuration == null ? true : (
      length(var.cors_configuration.allow_origins) > 0 &&
      var.cors_configuration.max_age_seconds >= 0 &&
      var.cors_configuration.max_age_seconds <= 86400 &&
      floor(var.cors_configuration.max_age_seconds) == var.cors_configuration.max_age_seconds &&
      !(
        var.cors_configuration.allow_credentials &&
        contains(var.cors_configuration.allow_origins, "*")
      )
    )
    error_message = "CORS requiere algún origen, max_age_seconds entre 0 y 86400 y no permite credenciales con el origen '*'."
  }
}

variable "throttling" {
  description = "Límites por defecto de ráfaga y solicitudes por segundo de API Gateway."
  type = object({
    burst_limit = number
    rate_limit  = number
  })
  default = {
    burst_limit = 50
    rate_limit  = 100
  }

  validation {
    condition = (
      var.throttling.burst_limit >= 0 &&
      var.throttling.rate_limit >= 0 &&
      floor(var.throttling.burst_limit) == var.throttling.burst_limit
    )
    error_message = "Los límites de throttling deben ser no negativos y burst_limit debe ser entero."
  }
}

variable "additional_tags" {
  description = "Etiquetas adicionales. Las etiquetas estructurales del módulo tienen prioridad."
  type        = map(string)
  default     = {}
}
