mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\":\"2012-10-17\",\"Statement\":[]}" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/test" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:eu-west-3:123456789012:log-group:test" }
  }
  mock_resource "aws_lambda_function" {
    defaults = { arn = "arn:aws:lambda:eu-west-3:123456789012:function:test" }
  }
  mock_resource "aws_sfn_state_machine" {
    defaults = { arn = "arn:aws:states:eu-west-3:123456789012:stateMachine:test" }
  }
  mock_resource "aws_sqs_queue" {
    defaults = { arn = "arn:aws:sqs:eu-west-3:123456789012:capture-failures" }
  }
}

run "captura_completa" {
  command = apply
  variables {
    documents_bucket = "bucket-de-prueba"
    image_uri        = "123456789012.dkr.ecr.eu-west-3.amazonaws.com/pipeline-fondos-dev-capture-scraper@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  assert {
    condition     = length(aws_lambda_function.scraper) == 3 && aws_scheduler_schedule.daily.state == "DISABLED"
    error_message = "Deben existir tres Lambdas y el horario debe empezar desactivado."
  }
  assert {
    condition = (
      aws_scheduler_schedule.daily.target[0].dead_letter_config[0].arn == aws_sqs_queue.scheduler_failures.arn &&
      aws_scheduler_schedule.daily.target[0].retry_policy[0].maximum_retry_attempts == 0 &&
      aws_sqs_queue.scheduler_failures.message_retention_seconds == 1209600 &&
      aws_sqs_queue.scheduler_failures.sqs_managed_sse_enabled &&
      aws_cloudwatch_metric_alarm.scheduler_failures.dimensions.QueueName == aws_sqs_queue.scheduler_failures.name &&
      length([for statement in jsondecode(aws_iam_role_policy.scheduler.policy).Statement : statement if statement.Action == ["sqs:SendMessage"] && statement.Resource == [aws_sqs_queue.scheduler_failures.arn]]) == 1
    )
    error_message = "Scheduler debe enviar fallos a su propia cola cifrada, con permiso acotado y alarma."
  }
  assert {
    condition     = length(jsondecode(aws_sfn_state_machine.capture.definition).States.Capturar.Branches) == 3
    error_message = "La máquina de estados debe tener tres ramas."
  }
  assert {
    condition = alltrue([
      for branch in jsondecode(aws_sfn_state_machine.capture.definition).States.Capturar.Branches :
      branch.States[branch.StartAt].Catch[0].Next == replace(branch.StartAt, "Invocar-", "Fallo-") &&
      branch.States[branch.StartAt].Retry[0].ErrorEquals == ["Lambda.TooManyRequestsException"]
    ])
    error_message = "Cada rama debe capturar su propio error."
  }
  assert {
    condition = (
      length(jsondecode(aws_sfn_state_machine.capture.definition).States.Comprobar.Choices[0].Or) == 3 &&
      alltrue([for choice in jsondecode(aws_sfn_state_machine.capture.definition).States.Comprobar.Choices[0].Or : choice.Not.StringEquals == "completa"]) &&
      jsondecode(aws_sfn_state_machine.capture.definition).States.Comprobar.Choices[0].Next == "CapturaFallida" &&
      aws_scheduler_schedule.daily.schedule_expression_timezone == "Europe/Madrid"
    )
    error_message = "Se deben revisar los tres estados y usar el huso de Madrid."
  }
}
