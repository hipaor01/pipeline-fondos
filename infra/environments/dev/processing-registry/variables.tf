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
  description = "Número de imágenes de procesamiento que se conservan en dev."
  type        = number
  default     = 15
}

variable "additional_tags" {
  description = "Etiquetas adicionales."
  type        = map(string)
  default     = {}
}
