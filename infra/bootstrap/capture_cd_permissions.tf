locals {
  p1_state_keys = [
    "${var.project_name}/${var.deployment_environment}/storage/terraform.tfstate",
    "${var.project_name}/${var.deployment_environment}/capture-registry/terraform.tfstate",
    "${var.project_name}/${var.deployment_environment}/capture/terraform.tfstate",
  ]
  p1_state_object_arns = flatten([
    for key in local.p1_state_keys : [
      "${aws_s3_bucket.terraform_state.arn}/${key}",
      "${aws_s3_bucket.terraform_state.arn}/${key}.tflock",
    ]
  ])
  p1_lock_object_arns = [
    for key in local.p1_state_keys : "${aws_s3_bucket.terraform_state.arn}/${key}.tflock"
  ]
  capture_repository_arn = "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${local.capture_repository_name}"
  capture_log_group_arns = flatten([
    for manager in ["bestinver", "azvalor", "cobas"] : [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.capture_name}-${manager}",
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${local.capture_name}-${manager}:*",
    ]
  ])
  capture_schedule_arn = "arn:aws:scheduler:${var.aws_region}:${data.aws_caller_identity.current.account_id}:schedule/default/${local.capture_name}-daily"
  capture_alarm_arn    = "arn:aws:cloudwatch:${var.aws_region}:${data.aws_caller_identity.current.account_id}:alarm:${local.capture_name}-scheduler-failures"
}

data "aws_iam_policy_document" "github_actions_capture_registry" {
  statement {
    sid    = "ReadAndWriteP1State"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = local.p1_state_object_arns
  }

  statement {
    sid       = "ReleaseP1StateLocks"
    effect    = "Allow"
    actions   = ["s3:DeleteObject"]
    resources = local.p1_lock_object_arns
  }

  statement {
    sid    = "InspectDocumentBucket"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:GetBucketPublicAccessBlock",
      "s3:GetBucketVersioning",
      "s3:GetEncryptionConfiguration",
      "s3:ListBucket",
    ]
    resources = [local.capture_documents_bucket_arn]
  }

  statement {
    sid    = "ManageCaptureRepository"
    effect = "Allow"
    actions = [
      "ecr:CreateRepository",
      "ecr:DeleteLifecyclePolicy",
      "ecr:DeleteRepository",
      "ecr:DeleteRepositoryPolicy",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:GetLifecyclePolicy",
      "ecr:GetRepositoryPolicy",
      "ecr:ListTagsForResource",
      "ecr:PutImageScanningConfiguration",
      "ecr:PutImageTagMutability",
      "ecr:PutLifecyclePolicy",
      "ecr:SetRepositoryPolicy",
      "ecr:TagResource",
      "ecr:UntagResource",
    ]
    resources = [local.capture_repository_arn]
  }

  statement {
    sid    = "PushCaptureImages"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [local.capture_repository_arn]
  }

  statement {
    sid       = "AuthenticateWithEcr"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "github_actions_capture_registry" {
  name        = "${local.cd_role_name}-capture-registry-policy"
  description = "P1 storage and capture state, bucket inspection and ECR deployment permissions"
  policy      = data.aws_iam_policy_document.github_actions_capture_registry.json

  tags = merge(
    local.common_tags,
    {
      Name        = "${local.cd_role_name}-capture-registry-policy"
      Environment = var.deployment_environment
      Purpose     = "github-actions-capture-cd"
    }
  )
}

resource "aws_iam_role_policy_attachment" "github_actions_capture_registry" {
  role       = aws_iam_role.github_actions_cd.name
  policy_arn = aws_iam_policy.github_actions_capture_registry.arn
}

data "aws_iam_policy_document" "github_actions_capture_services" {
  statement {
    sid       = "CreateCaptureRolesWithBoundary"
    effect    = "Allow"
    actions   = ["iam:CreateRole"]
    resources = local.capture_role_arns

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [local.capture_boundary_arn]
    }
  }

  statement {
    sid    = "ManageCaptureRoles"
    effect = "Allow"
    actions = [
      "iam:DeleteRole",
      "iam:DeleteRolePermissionsBoundary",
      "iam:DeleteRolePolicy",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRolePolicies",
      "iam:PutRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:UpdateRoleDescription",
    ]
    resources = local.capture_role_arns
  }

  statement {
    sid       = "MaintainCapturePermissionsBoundary"
    effect    = "Allow"
    actions   = ["iam:PutRolePermissionsBoundary"]
    resources = local.capture_role_arns

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [local.capture_boundary_arn]
    }
  }

  statement {
    sid       = "PassCaptureLambdaRoles"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = local.capture_lambda_role_arns

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }

  statement {
    sid       = "PassCaptureStatesRole"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [local.capture_states_role_arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["states.amazonaws.com"]
    }
  }

  statement {
    sid       = "PassCaptureSchedulerRole"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [local.capture_scheduler_role_arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["scheduler.amazonaws.com"]
    }
  }

  statement {
    sid    = "ManageCaptureLogGroups"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:DeleteRetentionPolicy",
      "logs:DescribeLogStreams",
      "logs:ListTagsForResource",
      "logs:ListTagsLogGroup",
      "logs:PutRetentionPolicy",
      "logs:TagResource",
      "logs:UntagResource",
    ]
    resources = local.capture_log_group_arns
  }

  statement {
    sid    = "ManageCaptureFunctions"
    effect = "Allow"
    actions = [
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:GetFunction",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:GetFunctionConfiguration",
      "lambda:GetPolicy",
      "lambda:ListTags",
      "lambda:ListVersionsByFunction",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
    ]
    resources = local.capture_lambda_function_arns
  }

  statement {
    sid    = "ManageCaptureStateMachine"
    effect = "Allow"
    actions = [
      "states:CreateStateMachine",
      "states:DeleteStateMachine",
      "states:DescribeStateMachine",
      "states:ListStateMachineVersions",
      "states:ListTagsForResource",
      "states:TagResource",
      "states:UntagResource",
      "states:UpdateStateMachine",
    ]
    resources = [local.capture_state_machine_arn]
  }

  statement {
    sid       = "ValidateCaptureStateMachine"
    effect    = "Allow"
    actions   = ["states:ValidateStateMachineDefinition"]
    resources = ["*"]
  }

  statement {
    sid    = "ManageCaptureSchedule"
    effect = "Allow"
    actions = [
      "scheduler:CreateSchedule",
      "scheduler:DeleteSchedule",
      "scheduler:GetSchedule",
      "scheduler:ListTagsForResource",
      "scheduler:TagResource",
      "scheduler:UntagResource",
      "scheduler:UpdateSchedule",
    ]
    resources = [local.capture_schedule_arn]
  }

  statement {
    sid    = "ManageCaptureFailureQueue"
    effect = "Allow"
    actions = [
      "sqs:CreateQueue",
      "sqs:DeleteQueue",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
      "sqs:ListQueueTags",
      "sqs:SetQueueAttributes",
      "sqs:TagQueue",
      "sqs:UntagQueue",
    ]
    resources = [local.capture_queue_arn]
  }

  statement {
    sid    = "ManageCaptureFailureAlarm"
    effect = "Allow"
    actions = [
      "cloudwatch:DeleteAlarms",
      "cloudwatch:DescribeAlarms",
      "cloudwatch:ListTagsForResource",
      "cloudwatch:PutMetricAlarm",
      "cloudwatch:TagResource",
      "cloudwatch:UntagResource",
    ]
    resources = [local.capture_alarm_arn]
  }
}

resource "aws_iam_policy" "github_actions_capture_services" {
  name        = "${local.cd_role_name}-capture-services-policy"
  description = "Least-privilege deployment permissions for capture services"
  policy      = data.aws_iam_policy_document.github_actions_capture_services.json

  tags = merge(
    local.common_tags,
    {
      Name        = "${local.cd_role_name}-capture-services-policy"
      Environment = var.deployment_environment
      Purpose     = "github-actions-capture-cd"
    }
  )
}

resource "aws_iam_role_policy_attachment" "github_actions_capture_services" {
  role       = aws_iam_role.github_actions_cd.name
  policy_arn = aws_iam_policy.github_actions_capture_services.arn
}
