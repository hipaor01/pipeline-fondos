variable "repository_name" {
  description = "Nombre del repositorio privado de ECR."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]+(?:[._/-][a-z0-9]+)*$", var.repository_name))
    error_message = "repository_name debe ser un nombre de repositorio ECR válido en minúsculas."
  }
}

variable "project_name" {
  description = "Nombre del proyecto."
  type        = string
  default     = "pipeline-fondos"
}

variable "environment" {
  description = "Entorno al que pertenece el repositorio."
  type        = string
}

variable "component" {
  description = "Componente propietario del repositorio."
  type        = string
  default     = "frontend"
}

variable "retained_image_count" {
  description = "Número máximo de imágenes que conserva la política de ciclo de vida."
  type        = number
  default     = 30

  validation {
    condition     = var.retained_image_count >= 1 && floor(var.retained_image_count) == var.retained_image_count
    error_message = "retained_image_count debe ser un número entero positivo."
  }
}

variable "expirable_tag_prefix" {
  description = "Si se indica, solo las imágenes con este prefijo pueden expirar."
  type        = string
  default     = null

  validation {
    condition     = var.expirable_tag_prefix == null ? true : can(regex("^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", var.expirable_tag_prefix))
    error_message = "expirable_tag_prefix debe ser un prefijo de etiqueta ECR no vacío."
  }
}

variable "additional_tags" {
  description = "Etiquetas adicionales del repositorio."
  type        = map(string)
  default     = {}
}
