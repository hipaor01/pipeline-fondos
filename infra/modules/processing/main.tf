# Capa de procesamiento (P2):
#
#   S3 raw/*_kid.pdf ──notificación S3──> SQS pdf ──> Lambda pdf-markdown ──> S3 processed/markdown/*.md
#   S3 processed/markdown/*.md ──notificación S3──> SQS markdown ──> Lambda extraccion ──> Bedrock
#                                                                    ├─> S3 processed/structured/*.json
#                                                                    └─> Aurora (Data API)
#
# Transporte acordado en el contrato C1 v1 (contracts/C1_PROPUESTA.md): notificación
# nativa S3 ObjectCreated -> SQS estándar. La configuración de notificaciones de un
# bucket es UN único recurso que reemplaza todo lo anterior; según
# contracts/INTEGRACION_P1_P2_P3_PROPUESTA.md la gestiona este estado (P2) y nadie
# más debe declarar otro aws_s3_bucket_notification para el mismo bucket.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  prefix     = "${var.project_name}-${var.environment}"
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region
  partition  = data.aws_partition.current.partition
  bucket_arn = "arn:${local.partition}:s3:::${var.documents_bucket_name}"

  common_tags = merge(
    var.additional_tags,
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
      Component   = "processing"
    }
  )

  # Dos etapas con la misma forma: cola + DLQ + regla + Lambda.
  stages = {
    markdown = {
      function_name = "${local.prefix}-pdf-markdown"
      handler       = "procesamiento.markdown.handler"
      description   = "PDF raw/ -> Markdown processed/markdown/ (contrato C2)"
      key_prefix    = "raw/"
      key_suffix    = "_kid.pdf" # C1: solo KID; las fichas se conservan pero no se procesan
      memory_mb     = var.markdown_memory_mb
      timeout_s     = var.markdown_timeout_seconds
      concurrency   = var.markdown_max_concurrency
    }
    extraccion = {
      function_name = "${local.prefix}-extraccion"
      handler       = "procesamiento.extraccion.handler"
      description   = "Markdown -> Bedrock -> JSON de auditoría y Aurora (contratos C3 y C4)"
      key_prefix    = "processed/markdown/"
      key_suffix    = ".md"
      memory_mb     = var.extraction_memory_mb
      timeout_s     = var.extraction_timeout_seconds
      concurrency   = var.extraction_max_concurrency
    }
  }

  common_environment = {
    SQS_MAX_RECEIVE_COUNT = tostring(var.max_receive_count)
  }

  stage_environment = {
    markdown = {
      MODO_OCR = var.ocr_mode
    }
    extraccion = {
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      BEDROCK_MAX_TOKENS = tostring(var.bedrock_max_tokens)
      DB_CLUSTER_ARN     = var.database_cluster_arn
      DB_SECRET_ARN      = var.database_secret_arn
      DB_NAME            = var.database_name
      TIPOS_KID          = jsonencode(var.kid_document_types)
    }
  }
}

# ------------------------------------------------------------------ SQS + DLQ

resource "aws_sqs_queue" "dlq" {
  for_each = local.stages

  name                      = "${each.value.function_name}-dlq"
  message_retention_seconds = 1209600 # 14 días para investigar y reprocesar
  sqs_managed_sse_enabled   = true

  tags = merge(local.common_tags, { Name = "${each.value.function_name}-dlq", Stage = each.key })
}

resource "aws_sqs_queue" "this" {
  for_each = local.stages

  name                       = each.value.function_name
  visibility_timeout_seconds = each.value.timeout_s * 6 # recomendación de AWS para Lambda + SQS
  message_retention_seconds  = 345600                   # 4 días
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = merge(local.common_tags, { Name = each.value.function_name, Stage = each.key })
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  for_each = local.stages

  queue_url = aws_sqs_queue.dlq[each.key].id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.this[each.key].arn]
  })
}

# ------------------------------------------------------------------ Notificaciones S3

data "aws_iam_policy_document" "queue" {
  for_each = local.stages

  statement {
    sid       = "AllowDocumentsBucket"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.this[each.key].arn]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [local.bucket_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sqs_queue_policy" "this" {
  for_each = local.stages

  queue_url = aws_sqs_queue.this[each.key].id
  policy    = data.aws_iam_policy_document.queue[each.key].json
}

# Al crearla, S3 valida cada destino enviando un s3:TestEvent: la política de las
# colas debe existir antes. Los handlers ignoran ese evento.
resource "aws_s3_bucket_notification" "documents" {
  count  = var.manage_bucket_notifications ? 1 : 0
  bucket = var.documents_bucket_name

  dynamic "queue" {
    for_each = local.stages
    content {
      id            = "${local.prefix}-${queue.key}"
      queue_arn     = aws_sqs_queue.this[queue.key].arn
      events        = ["s3:ObjectCreated:*"]
      filter_prefix = queue.value.key_prefix
      filter_suffix = queue.value.key_suffix
    }
  }

  depends_on = [aws_sqs_queue_policy.this]
}

# ------------------------------------------------------------------ Lambda

resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.stages

  name              = "/aws/lambda/${each.value.function_name}"
  retention_in_days = var.log_retention_days

  tags = merge(local.common_tags, { Stage = each.key })
}

resource "aws_lambda_function" "this" {
  for_each = local.stages

  function_name = each.value.function_name
  description   = each.value.description
  role          = aws_iam_role.lambda[each.key].arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = [var.lambda_architecture]
  memory_size   = each.value.memory_mb
  timeout       = each.value.timeout_s

  image_config {
    command = [each.value.handler]
  }

  environment {
    variables = merge(local.common_environment, local.stage_environment[each.key])
  }

  logging_config {
    log_format = "Text" # los handlers ya escriben JSON con correlation_id
    log_group  = aws_cloudwatch_log_group.lambda[each.key].name
  }

  tags = merge(local.common_tags, { Name = each.value.function_name, Stage = each.key })

  depends_on = [aws_iam_role_policy.lambda]
}

resource "aws_lambda_event_source_mapping" "this" {
  for_each = local.stages

  event_source_arn        = aws_sqs_queue.this[each.key].arn
  function_name           = aws_lambda_function.this[each.key].arn
  batch_size              = 1
  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = each.value.concurrency
  }

  tags = merge(local.common_tags, { Stage = each.key })
}
