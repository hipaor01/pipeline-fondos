locals {
  deployment_state_keys = [
    "${var.project_name}/${var.deployment_environment}/terraform.tfstate",
    "${var.project_name}/${var.deployment_environment}/artifacts/terraform.tfstate",
  ]

  deployment_state_object_arns = flatten([
    for key in local.deployment_state_keys : [
      "${aws_s3_bucket.terraform_state.arn}/${key}",
      "${aws_s3_bucket.terraform_state.arn}/${key}.tflock",
    ]
  ])

  deployment_lock_object_arns = [
    for key in local.deployment_state_keys : "${aws_s3_bucket.terraform_state.arn}/${key}.tflock"
  ]

  lambda_function_arn = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-${var.deployment_environment}-api"
  lambda_role_arn     = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/${local.lambda_execution_role_name}"

  log_group_arns = [
    "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.deployment_environment}-api",
    "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.project_name}-${var.deployment_environment}-api:*",
    "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/apigateway/${var.project_name}-${var.deployment_environment}-http-api",
    "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/apigateway/${var.project_name}-${var.deployment_environment}-http-api:*",
  ]
}

data "aws_iam_policy_document" "github_actions_cd" {
  statement {
    sid    = "ListDeploymentState"
    effect = "Allow"
    actions = [
      "s3:ListBucket",
    ]
    resources = [aws_s3_bucket.terraform_state.arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${var.project_name}/${var.deployment_environment}/*"]
    }
  }

  statement {
    sid    = "ReadAndWriteDeploymentState"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = local.deployment_state_object_arns
  }

  statement {
    sid       = "ReleaseDeploymentStateLocks"
    effect    = "Allow"
    actions   = ["s3:DeleteObject"]
    resources = local.deployment_lock_object_arns
  }

  statement {
    sid    = "ManageArtifactBucket"
    effect = "Allow"
    actions = [
      "s3:*",
    ]
    resources = [
      "arn:aws:s3:::${local.artifact_bucket_name}",
      "arn:aws:s3:::${local.artifact_bucket_name}/*",
    ]
  }

  statement {
    sid    = "ManageApiLambda"
    effect = "Allow"
    actions = [
      "lambda:AddPermission",
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:GetFunction",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:GetFunctionConfiguration",
      "lambda:GetPolicy",
      "lambda:ListTags",
      "lambda:RemovePermission",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
    ]
    resources = [local.lambda_function_arn]
  }

  statement {
    sid       = "CreateLambdaExecutionRoleWithBoundary"
    effect    = "Allow"
    actions   = ["iam:CreateRole"]
    resources = [local.lambda_role_arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.lambda_execution_boundary.arn]
    }
  }

  statement {
    sid    = "ManageLambdaExecutionRole"
    effect = "Allow"
    actions = [
      "iam:DeleteRole",
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
    resources = [local.lambda_role_arn]
  }

  statement {
    sid       = "MaintainLambdaPermissionsBoundary"
    effect    = "Allow"
    actions   = ["iam:PutRolePermissionsBoundary"]
    resources = [local.lambda_role_arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.lambda_execution_boundary.arn]
    }
  }

  statement {
    sid       = "PassLambdaExecutionRole"
    effect    = "Allow"
    actions   = ["iam:PassRole"]
    resources = [local.lambda_role_arn]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }

  statement {
    sid    = "ManageApiLogGroups"
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
    resources = local.log_group_arns
  }

  statement {
    sid       = "DiscoverApiLogGroups"
    effect    = "Allow"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }

  statement {
    sid    = "ManageApiLogDelivery"
    effect = "Allow"
    actions = [
      "logs:CreateLogDelivery",
      "logs:DeleteLogDelivery",
      "logs:DescribeResourcePolicies",
      "logs:GetLogDelivery",
      "logs:ListLogDeliveries",
      "logs:PutResourcePolicy",
      "logs:UpdateLogDelivery",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ManageHttpApis"
    effect = "Allow"
    actions = [
      "apigateway:DELETE",
      "apigateway:GET",
      "apigateway:PATCH",
      "apigateway:POST",
      "apigateway:PUT",
    ]
    resources = ["arn:aws:apigateway:${var.aws_region}::/apis*"]
  }

  statement {
    sid       = "ReadCallerIdentity"
    effect    = "Allow"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "github_actions_cd" {
  name        = "${local.cd_role_name}-policy"
  description = "Least-privilege deployment permissions for ${var.project_name} ${var.deployment_environment}"
  policy      = data.aws_iam_policy_document.github_actions_cd.json

  tags = merge(
    local.common_tags,
    {
      Name        = "${local.cd_role_name}-policy"
      Environment = var.deployment_environment
      Purpose     = "github-actions-cd"
    }
  )
}

resource "aws_iam_role_policy_attachment" "github_actions_cd" {
  role       = aws_iam_role.github_actions_cd.name
  policy_arn = aws_iam_policy.github_actions_cd.arn
}
