variable "project_name" {
  description = "Nombre corto del proyecto."
  type        = string
  default     = "pipeline-fondos"
}

variable "environment" {
  description = "Entorno de despliegue."
  type        = string
}

variable "documents_bucket_name" {
  description = "Bucket de documentos de P1 (C1). Debe tener activadas las notificaciones a EventBridge."
  type        = string
}

variable "documents_bucket_kms_key_arn" {
  description = "Clave KMS del bucket si usa SSE-KMS; null si usa SSE-S3."
  type        = string
  default     = null
}

variable "image_uri" {
  description = "Imagen de las Lambdas por digest (repositorio@sha256:...)."
  type        = string

  validation {
    condition     = can(regex("@sha256:[a-f0-9]{64}$", var.image_uri))
    error_message = "image_uri debe referenciar la imagen por digest (…@sha256:…), nunca por etiqueta."
  }
}

variable "lambda_architecture" {
  description = "Arquitectura de la imagen: arm64 (Graviton, más barata) o x86_64."
  type        = string
  default     = "arm64"

  validation {
    condition     = contains(["arm64", "x86_64"], var.lambda_architecture)
    error_message = "lambda_architecture debe ser arm64 o x86_64."
  }
}

variable "permissions_boundary_arn" {
  description = "Permissions boundary de los roles de ejecución (la exige el rol de CD)."
  type        = string
  default     = null
}

variable "bedrock_model_id" {
  description = "Modelo o perfil de inferencia de Bedrock con soporte de salidas estructuradas."
  type        = string
}

variable "bedrock_max_tokens" {
  description = "Tokens máximos de la respuesta del modelo."
  type        = number
  default     = 2000
}

variable "database_cluster_arn" {
  description = "ARN del clúster Aurora (módulo database)."
  type        = string
}

variable "database_secret_arn" {
  description = "ARN del secreto de la base de datos (módulo database)."
  type        = string
}

variable "database_name" {
  description = "Nombre de la base de datos."
  type        = string
  default     = "fondos"
}

variable "kid_document_types" {
  description = "Valores de tipo_documento que se envían a Bedrock; el resto se audita como REJECTED."
  type        = list(string)
  default     = ["datos_fundamentales"]
}

variable "ocr_mode" {
  description = "OCR en la conversión: nunca (por defecto), auto o siempre. auto/siempre requieren OCR en la imagen."
  type        = string
  default     = "nunca"

  validation {
    condition     = contains(["nunca", "auto", "siempre"], var.ocr_mode)
    error_message = "ocr_mode debe ser nunca, auto o siempre."
  }
}

variable "max_receive_count" {
  description = "Intentos antes de mover un mensaje a la DLQ."
  type        = number
  default     = 3
}

variable "markdown_memory_mb" {
  type    = number
  default = 2048
}

variable "markdown_timeout_seconds" {
  type    = number
  default = 120
}

variable "markdown_max_concurrency" {
  description = "Máximo de Lambdas de conversión en paralelo (mínimo 2 en SQS)."
  type        = number
  default     = 2
}

variable "extraction_memory_mb" {
  type    = number
  default = 512
}

variable "extraction_timeout_seconds" {
  description = "Incluye la compilación del esquema en la primera llamada a Bedrock (hasta ~90 s)."
  type        = number
  default     = 300
}

variable "extraction_max_concurrency" {
  description = "Máximo de extracciones en paralelo: limita la presión sobre Bedrock y Aurora."
  type        = number
  default     = 2
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "additional_tags" {
  type    = map(string)
  default = {}
}
