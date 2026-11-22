variable "aws_region" {
  description = "Región del servicio ECS Express."
  type        = string
  default     = "eu-west-3"
}

variable "project_name" {
  description = "Nombre del proyecto."
  type        = string
  default     = "pipeline-fondos"
}

variable "frontend_image" {
  description = "Imagen ECR ARM64 inmutable identificada por digest."
  type        = string
}

variable "cpu_units" {
  description = "Unidades de CPU reservadas por tarea del frontend."
  type        = number
  default     = 512
}

variable "memory_mib" {
  description = "Memoria en MiB reservada por tarea del frontend."
  type        = number
  default     = 1024
}

variable "min_task_count" {
  description = "Número mínimo de tareas activas."
  type        = number
  default     = 1
}

variable "max_task_count" {
  description = "Número máximo de tareas activas."
  type        = number
  default     = 2
}

variable "log_retention_days" {
  description = "Retención de logs de Streamlit en días."
  type        = number
  default     = 14
}

variable "additional_tags" {
  description = "Etiquetas adicionales."
  type        = map(string)
  default     = {}
}
