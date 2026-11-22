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

variable "retained_image_count" {
  description = "Número máximo de imágenes que conserva la política de ciclo de vida."
  type        = number
  default     = 30

  validation {
    condition     = var.retained_image_count >= 1 && floor(var.retained_image_count) == var.retained_image_count
    error_message = "retained_image_count debe ser un número entero positivo."
  }
}

variable "additional_tags" {
  description = "Etiquetas adicionales del repositorio."
  type        = map(string)
  default     = {}
}
