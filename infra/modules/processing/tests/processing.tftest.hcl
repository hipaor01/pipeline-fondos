# terraform -chdir=infra/modules/processing init -backend=false && terraform -chdir=infra/modules/processing test
# Usa un proveedor simulado: no necesita credenciales de AWS.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_region" {
    defaults = { region = "eu-west-3" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/rol" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:eu-west-3:123456789012:log-group:grupo" }
  }
  mock_resource "aws_lambda_function" {
    defaults = { arn = "arn:aws:lambda:eu-west-3:123456789012:function:f" }
  }
  mock_resource "aws_sqs_queue" {
    defaults = { arn = "arn:aws:sqs:eu-west-3:123456789012:cola" }
  }
}

variables {
  environment           = "test"
  documents_bucket_name = "bucket-documentos"
  image_uri             = "123456789012.dkr.ecr.eu-west-3.amazonaws.com/proc@sha256:0000000000000000000000000000000000000000000000000000000000000000"
  bedrock_model_id      = "global.moonshotai.kimi-k3.1"
  database_cluster_arn  = "arn:aws:rds:eu-west-3:123456789012:cluster:c"
  database_secret_arn   = "arn:aws:secretsmanager:eu-west-3:123456789012:secret:s"
}

run "perfil_de_inferencia_global" {
  command = plan

  assert {
    condition = jsonencode(local.bedrock_resources) == jsonencode([
      "arn:aws:bedrock:eu-west-3:123456789012:inference-profile/global.moonshotai.kimi-k3.1",
      "arn:aws:bedrock:*::foundation-model/moonshotai.kimi-k3.1",
      "arn:aws:bedrock:::foundation-model/moonshotai.kimi-k3.1",
    ])
    error_message = "Permisos de Bedrock incorrectos para un perfil global: ${jsonencode(local.bedrock_resources)}"
  }
}

run "modelo_base_sin_perfil" {
  command = plan

  variables {
    bedrock_model_id = "mistral.mistral-large-3"
  }

  assert {
    condition     = jsonencode(local.bedrock_resources) == jsonencode(["arn:aws:bedrock:eu-west-3::foundation-model/mistral.mistral-large-3"])
    error_message = "Un modelo base solo debe tener permiso sobre sí mismo en la región."
  }
}

run "colas_y_lambdas" {
  command = apply

  assert {
    condition     = aws_lambda_event_source_mapping.this["markdown"].batch_size == 1 && aws_lambda_event_source_mapping.this["extraccion"].batch_size == 1
    error_message = "El contrato exige batch=1."
  }

  assert {
    condition     = jsondecode(aws_sqs_queue.this["extraccion"].redrive_policy).maxReceiveCount == 3
    error_message = "La cola de extracción debe tener DLQ tras 3 intentos."
  }

  assert {
    condition     = aws_sqs_queue.this["extraccion"].visibility_timeout_seconds >= 6 * aws_lambda_function.this["extraccion"].timeout
    error_message = "La visibilidad de la cola debe ser al menos 6 veces el timeout de la Lambda."
  }

  assert {
    condition     = jsonencode(aws_lambda_function.this["extraccion"].image_config[0].command) == jsonencode(["procesamiento.extraccion.handler"])
    error_message = "Handler de extracción incorrecto."
  }

  assert {
    condition     = one([for q in aws_s3_bucket_notification.documents[0].queue : q if q.filter_prefix == "raw/"]).filter_suffix == "_kid.pdf"
    error_message = "La notificación de conversión debe filtrar raw/ + _kid.pdf (contrato C1)."
  }

  assert {
    condition     = jsonencode(local.s3_write_prefixes["extraccion"]) == jsonencode(["processed/structured/*"])
    error_message = "La extracción solo puede escribir en processed/structured/."
  }
}

run "notificacion_completa_del_bucket" {
  command = apply

  assert {
    condition     = length(aws_s3_bucket_notification.documents[0].queue) == 2
    error_message = "La configuración del bucket debe declarar las dos colas de P2 en un único recurso."
  }

  assert {
    condition     = one([for q in aws_s3_bucket_notification.documents[0].queue : q if q.filter_prefix == "processed/markdown/"]).filter_suffix == ".md"
    error_message = "La extracción solo debe recibir processed/markdown/*.md."
  }
}

run "sin_gestionar_notificaciones" {
  command = plan

  variables {
    manage_bucket_notifications = false
  }

  assert {
    condition     = length(aws_s3_bucket_notification.documents) == 0
    error_message = "Con manage_bucket_notifications = false no se toca el bucket."
  }
}

run "imagen_por_etiqueta_se_rechaza" {
  command = plan

  variables {
    image_uri = "123456789012.dkr.ecr.eu-west-3.amazonaws.com/proc:latest"
  }

  expect_failures = [var.image_uri]
}
