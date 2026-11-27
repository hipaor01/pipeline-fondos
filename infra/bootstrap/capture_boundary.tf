locals {
  capture_name                 = "${var.project_name}-${var.deployment_environment}-capture"
  capture_repository_name      = "${local.capture_name}-scraper"
  capture_boundary_name        = "${local.capture_name}-boundary"
  capture_boundary_arn         = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${local.capture_boundary_name}"
  capture_documents_bucket_arn = "arn:aws:s3:::${var.capture_documents_bucket}"

  capture_lambda_function_arns = [
    for manager in ["bestinver", "azvalor", "cobas"] :
    "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${local.capture_name}-${manager}"
  ]
  capture_lambda_role_arns = [
    for manager in ["bestinver", "azvalor", "cobas"] :
    "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.capture_name}-${manager}"
  ]
  capture_states_role_arn    = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.capture_name}-states"
  capture_scheduler_role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.capture_name}-scheduler"
  capture_role_arns          = concat(local.capture_lambda_role_arns, [local.capture_states_role_arn, local.capture_scheduler_role_arn])
  capture_state_machine_arn  = "arn:aws:states:${var.aws_region}:${data.aws_caller_identity.current.account_id}:stateMachine:${local.capture_name}"
  capture_queue_arn          = "arn:aws:sqs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:${local.capture_name}-scheduler-failures"
}

data "aws_iam_policy_document" "capture_execution_boundary" {
  statement {
    sid    = "WriteCaptureLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      for function_arn in local.capture_lambda_function_arns :
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${element(split(":", function_arn), 6)}:*"
    ]
  }

  statement {
    sid    = "ReadDocumentBucketConfiguration"
    effect = "Allow"
    actions = [
      "s3:GetBucketVersioning",
      "s3:ListBucket",
    ]
    resources = [local.capture_documents_bucket_arn]
  }

  statement {
    sid     = "WriteCapturedDocuments"
    effect  = "Allow"
    actions = ["s3:PutObject"]
    resources = [
      "${local.capture_documents_bucket_arn}/raw/*",
      "${local.capture_documents_bucket_arn}/manifests/*",
    ]
  }

  statement {
    sid       = "InvokeCaptureFunctions"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = local.capture_lambda_function_arns
  }

  statement {
    sid       = "StartCaptureStateMachine"
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [local.capture_state_machine_arn]
  }

  statement {
    sid       = "ReportSchedulerFailures"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [local.capture_queue_arn]
  }
}

resource "aws_iam_policy" "capture_execution_boundary" {
  name        = local.capture_boundary_name
  description = "Maximum permissions for ${local.capture_name} service roles"
  policy      = data.aws_iam_policy_document.capture_execution_boundary.json

  tags = merge(
    local.common_tags,
    {
      Name        = local.capture_boundary_name
      Environment = var.deployment_environment
      Purpose     = "capture-permissions-boundary"
    }
  )
}
