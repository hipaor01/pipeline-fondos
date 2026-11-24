data "aws_caller_identity" "current" {}

locals {
  name     = "${var.project_name}-dev-capture"
  gestoras = toset(["bestinver", "azvalor", "cobas"])
  tags     = { Project = var.project_name, Environment = "dev", ManagedBy = "Terraform", Component = "capture" }
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.gestoras
  name              = "/aws/lambda/${local.name}-${each.key}"
  retention_in_days = 14
  tags              = local.tags
}

resource "aws_iam_role" "lambda" {
  for_each           = local.gestoras
  name               = "${local.name}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
  tags               = local.tags
}

data "aws_iam_policy_document" "lambda" {
  for_each = local.gestoras
  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketVersioning"]
    resources = ["arn:aws:s3:::${var.documents_bucket}"]
  }
  statement {
    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::${var.documents_bucket}/raw/${each.key}/*", "arn:aws:s3:::${var.documents_bucket}/manifests/${each.key}/*"]
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda[each.key].arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  for_each = local.gestoras
  role     = aws_iam_role.lambda[each.key].id
  policy   = data.aws_iam_policy_document.lambda[each.key].json
}

resource "aws_lambda_function" "scraper" {
  for_each      = local.gestoras
  function_name = "${local.name}-${each.key}"
  role          = aws_iam_role.lambda[each.key].arn
  package_type  = "Image"
  image_uri     = var.image_uri
  architectures = ["arm64"]
  timeout       = 900
  memory_size   = 512
  environment {
    variables = { GESTORA = each.key, BUCKET_DOCUMENTOS = var.documents_bucket }
  }
  lifecycle {
    precondition {
      condition     = startswith(var.image_uri, "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/${local.name}-scraper@sha256:")
      error_message = "La imagen debe pertenecer al repositorio de captura de esta cuenta y región."
    }
  }
  tags       = local.tags
  depends_on = [aws_iam_role_policy.lambda]
}

data "aws_iam_policy_document" "states_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "states" {
  name               = "${local.name}-states"
  assume_role_policy = data.aws_iam_policy_document.states_trust.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "states" {
  role = aws_iam_role.states.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = ["lambda:InvokeFunction"], Resource = [for fn in aws_lambda_function.scraper : fn.arn]
  }] })
}

resource "aws_sfn_state_machine" "capture" {
  name     = local.name
  role_arn = aws_iam_role.states.arn
  type     = "STANDARD"
  definition = jsonencode({
    StartAt = "Capturar"
    States = {
      Capturar = {
        Type = "Parallel"
        Branches = [for gestora in ["bestinver", "azvalor", "cobas"] : {
          StartAt = "Invocar-${gestora}"
          States = {
            "Invocar-${gestora}" = {
              Type     = "Task"
              Resource = "arn:aws:states:::lambda:invoke"
              Parameters = {
                FunctionName = aws_lambda_function.scraper[gestora].arn
                Payload      = { "correlation_id.$" = "$$.Execution.Name" }
              }
              ResultSelector = { "gestora.$" = "$.Payload.gestora", "estado.$" = "$.Payload.estado", "subidos.$" = "$.Payload.subidos", "fallos.$" = "$.Payload.fallos" }
              Retry          = [{ ErrorEquals = ["Lambda.TooManyRequestsException"], IntervalSeconds = 2, MaxAttempts = 2, BackoffRate = 2 }]
              Catch          = [{ ErrorEquals = ["States.ALL"], ResultPath = "$.error", Next = "Fallo-${gestora}" }]
              End            = true
            }
            "Fallo-${gestora}" = { Type = "Pass", Parameters = { gestora = gestora, estado = "fallida", "error.$" = "$.error.Error" }, End = true }
          }
        }]
        ResultPath = "$.resultados"
        Next       = "Comprobar"
      }
      Comprobar = {
        Type = "Choice"
        Choices = [{
          Or   = [for i in range(3) : { Not = { Variable = "$.resultados[${i}].estado", StringEquals = "completa" } }]
          Next = "CapturaFallida"
        }]
        Default = "CapturaCompleta"
      }
      CapturaFallida  = { Type = "Fail", Error = "CapturaIncompleta", Cause = "Al menos una gestora ha fallado o terminado parcialmente; consultar el historial." }
      CapturaCompleta = { Type = "Succeed" }
    }
  })
  tags       = local.tags
  depends_on = [aws_iam_role_policy.states]
}

data "aws_iam_policy_document" "scheduler_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_trust.json
  tags               = local.tags
}

resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = ["states:StartExecution"], Resource = [aws_sfn_state_machine.capture.arn]
  }] })
}

resource "aws_scheduler_schedule" "daily" {
  name                         = "${local.name}-daily"
  state                        = var.schedule_enabled ? "ENABLED" : "DISABLED"
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = "Europe/Madrid"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_sfn_state_machine.capture.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = "{}"
    retry_policy {
      maximum_event_age_in_seconds = 60
      maximum_retry_attempts       = 0
    }
  }
  depends_on = [aws_iam_role_policy.scheduler]
}
