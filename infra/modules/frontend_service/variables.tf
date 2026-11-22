variable "service_name" {
  description = "Nombre estable del servicio ECS Express."
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{1,64}$", var.service_name))
    error_message = "service_name debe contener como máximo 64 letras, números, guiones o guiones bajos."
  }
}

variable "container_image" {
  description = "Imagen ECR inmutable identificada por digest SHA-256."
  type        = string

  validation {
    condition = can(regex(
      "^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$",
      var.container_image,
    ))
    error_message = "container_image debe ser una imagen privada de ECR identificada por digest SHA-256."
  }
}

variable "api_base_url" {
  description = "Endpoint HTTPS de la API consumida por Streamlit."
  type        = string

  validation {
    condition     = can(regex("^https://[^/]+(?:/.*)?$", var.api_base_url))
    error_message = "api_base_url debe ser una URL HTTPS válida."
  }
}

variable "api_timeout_seconds" {
  description = "Timeout de las llamadas del frontend a la API."
  type        = number
  default     = 10

  validation {
    condition     = var.api_timeout_seconds > 0
    error_message = "api_timeout_seconds debe ser mayor que cero."
  }
}

variable "container_port" {
  description = "Puerto TCP en el que escucha Streamlit."
  type        = number
  default     = 8501

  validation {
    condition     = var.container_port >= 1 && var.container_port <= 65535
    error_message = "container_port debe ser un puerto TCP válido."
  }
}

variable "health_check_path" {
  description = "Ruta HTTP que consulta el balanceador."
  type        = string
  default     = "/_stcore/health"

  validation {
    condition     = startswith(var.health_check_path, "/")
    error_message = "health_check_path debe comenzar por '/'."
  }
}

variable "cpu_units" {
  description = "Unidades de CPU reservadas por tarea."
  type        = number
  default     = 512

  validation {
    condition     = contains([256, 512, 1024], var.cpu_units)
    error_message = "cpu_units debe ser 256, 512 o 1024."
  }
}

variable "memory_mib" {
  description = "Memoria reservada por tarea en MiB."
  type        = number
  default     = 1024

  validation {
    condition     = var.memory_mib >= 512 && var.memory_mib <= 8192
    error_message = "memory_mib debe estar entre 512 y 8192."
  }
}

variable "min_task_count" {
  description = "Número mínimo de tareas siempre activas."
  type        = number
  default     = 1

  validation {
    condition     = var.min_task_count >= 1 && floor(var.min_task_count) == var.min_task_count
    error_message = "min_task_count debe ser un entero mayor o igual que uno."
  }
}

variable "max_task_count" {
  description = "Número máximo de tareas permitido por el autoescalado."
  type        = number
  default     = 2

  validation {
    condition     = var.max_task_count >= 1 && floor(var.max_task_count) == var.max_task_count
    error_message = "max_task_count debe ser un entero mayor o igual que uno."
  }
}

variable "log_retention_days" {
  description = "Días de retención de los logs del frontend."
  type        = number
  default     = 14
}

variable "project_name" {
  description = "Nombre del proyecto."
  type        = string
  default     = "pipeline-fondos"
}

variable "environment" {
  description = "Entorno del servicio."
  type        = string
}

variable "aws_region" {
  description = "Región AWS del servicio."
  type        = string
}

variable "additional_tags" {
  description = "Etiquetas adicionales del servicio."
  type        = map(string)
  default     = {}
}
