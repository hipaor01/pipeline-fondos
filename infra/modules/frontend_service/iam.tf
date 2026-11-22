data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "task_execution_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:ecs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${var.service_name}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.task_execution_assume_role.json

  tags = merge(
    local.common_tags,
    {
      Name    = "${var.service_name}-task-execution"
      Purpose = "ecs-task-execution"
    }
  )
}

resource "aws_iam_role_policy_attachment" "task_execution" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "infrastructure_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "infrastructure" {
  name               = "${var.service_name}-infrastructure"
  assume_role_policy = data.aws_iam_policy_document.infrastructure_assume_role.json

  tags = merge(
    local.common_tags,
    {
      Name    = "${var.service_name}-infrastructure"
      Purpose = "ecs-express-infrastructure"
    }
  )
}

resource "aws_iam_role_policy_attachment" "infrastructure" {
  role       = aws_iam_role.infrastructure.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices"
}

resource "time_sleep" "iam_propagation" {
  create_duration = "60s"

  depends_on = [
    aws_iam_role_policy_attachment.infrastructure,
    aws_iam_role_policy_attachment.task_execution,
  ]
}
