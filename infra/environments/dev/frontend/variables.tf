variable "aws_region" {
  description = "Región del repositorio de contenedores."
  type        = string
  default     = "eu-west-3"
}

variable "project_name" {
  description = "Nombre del proyecto."
  type        = string
  default     = "pipeline-fondos"
}

variable "retained_image_count" {
  description = "Número de imágenes del frontend que se conservan en dev."
  type        = number
  default     = 30

  validation {
    condition     = var.retained_image_count >= 1 && floor(var.retained_image_count) == var.retained_image_count
    error_message = "retained_image_count debe ser un número entero positivo."
  }
}

variable "additional_tags" {
  description = "Etiquetas adicionales."
  type        = map(string)
  default     = {}
}
