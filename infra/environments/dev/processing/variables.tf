variable "aws_region" {
  description = "Región de despliegue."
  type        = string
  default     = "eu-west-3"
}

variable "project_name" {
  description = "Nombre del proyecto."
  type        = string
  default     = "pipeline-fondos"
}

variable "documents_bucket_name" {
  description = "Bucket de documentos de P1 (output bucket_name de dev/storage; variable de repositorio CAPTURE_DOCUMENTS_BUCKET)."
  type        = string
}

variable "manage_bucket_notifications" {
  description = "P2 gestiona la configuración completa de notificaciones del bucket (contracts/INTEGRACION_P1_P2_P3_PROPUESTA.md)."
  type        = bool
  default     = true
}

variable "image_uri" {
  description = "Imagen de procesamiento por digest; la pipeline la pasa como TF_VAR_image_uri."
  type        = string
}

variable "lambda_architecture" {
  description = "Arquitectura con la que se construyó la imagen."
  type        = string
  default     = "arm64"
}

variable "bedrock_model_id" {
  description = "Modelo o perfil de inferencia de Bedrock. Debe admitir salidas estructuradas en eu-west-3."
  type        = string
  default     = "global.moonshotai.kimi-k3.1"
}

variable "database_name" {
  description = "Base de datos de Aurora."
  type        = string
  default     = "fondos"
}

variable "database_max_capacity" {
  description = "ACU máximas de Aurora Serverless v2."
  type        = number
  default     = 2
}

variable "database_deletion_protection" {
  description = "Protección contra borrado del clúster."
  type        = bool
  default     = false
}

variable "additional_tags" {
  description = "Etiquetas adicionales."
  type        = map(string)
  default     = {}
}
