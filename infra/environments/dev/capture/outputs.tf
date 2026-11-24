output "lambda_names" {
  value = { for name, fn in aws_lambda_function.scraper : name => fn.function_name }
}

output "state_machine_arn" {
  value = aws_sfn_state_machine.capture.arn
}

output "scheduler_role_arn" {
  value = aws_iam_role.scheduler.arn
}

output "schedule_name" {
  value = aws_scheduler_schedule.daily.name
}
