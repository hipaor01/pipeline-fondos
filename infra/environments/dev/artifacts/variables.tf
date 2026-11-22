variable "aws_region" {
  description = "Región del bucket de artefactos."
  type        = string
  default     = "eu-west-3"
}

variable "project_name" {
  description = "Nombre del proyecto."
  type        = string
  default     = "pipeline-fondos"
}

variable "artifact_retention_days" {
  description = "Retención de los ZIP de la API en dev."
  type        = number
  default     = 30
}

variable "additional_tags" {
  description = "Etiquetas adicionales."
  type        = map(string)
  default     = {}
}
