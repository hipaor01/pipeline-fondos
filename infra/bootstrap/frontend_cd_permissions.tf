data "aws_iam_policy_document" "github_actions_frontend" {
  statement {
    sid    = "ReadAndWriteFrontendState"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = local.frontend_state_object_arns
  }

  statement {
    sid       = "ReleaseFrontendStateLocks"
    effect    = "Allow"
    actions   = ["s3:DeleteObject"]
    resources = local.frontend_lock_object_arns
  }

  statement {
    sid    = "ManageFrontendRepository"
    effect = "Allow"
    actions = [
      "ecr:CreateRepository",
      "ecr:DeleteLifecyclePolicy",
      "ecr:DeleteRepository",
      "ecr:DescribeImages",
      "ecr:DescribeRepositories",
      "ecr:GetLifecyclePolicy",
      "ecr:ListTagsForResource",
      "ecr:PutImageScanningConfiguration",
      "ecr:PutImageTagMutability",
      "ecr:PutLifecyclePolicy",
      "ecr:TagResource",
      "ecr:UntagResource",
    ]
    resources = [local.frontend_repository_arn]
  }

  statement {
    sid    = "PushFrontendImages"
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = [local.frontend_repository_arn]
  }

  statement {
    sid       = "AuthenticateWithEcr"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid    = "ManageFrontendLogGroup"
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
    resources = local.frontend_log_group_arns
  }

  statement {
    sid    = "ManageFrontendServiceRoles"
    effect = "Allow"
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRolePolicies",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:UpdateRoleDescription",
    ]
    resources = [
      local.frontend_task_execution_role_arn,
      local.frontend_infrastructure_role_arn,
    ]
  }

  statement {
    sid    = "AttachFrontendServicePolicies"
    effect = "Allow"
    actions = [
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
    ]
    resources = [
      local.frontend_task_execution_role_arn,
      local.frontend_infrastructure_role_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "iam:PolicyARN"
      values = [
        "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
        "arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices",
      ]
    }
  }

  statement {
    sid     = "PassFrontendServiceRoles"
    effect  = "Allow"
    actions = ["iam:PassRole"]
    resources = [
      local.frontend_task_execution_role_arn,
      local.frontend_infrastructure_role_arn,
    ]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values = [
        "ecs-tasks.amazonaws.com",
        "ecs.amazonaws.com",
      ]
    }
  }

  statement {
    sid    = "ManageFrontendExpressService"
    effect = "Allow"
    actions = [
      "ecs:CreateExpressGatewayService",
      "ecs:DeleteExpressGatewayService",
      "ecs:DescribeExpressGatewayService",
      "ecs:DescribeServices",
      "ecs:ListTagsForResource",
      "ecs:TagResource",
      "ecs:UntagResource",
      "ecs:UpdateExpressGatewayService",
    ]
    resources = [local.frontend_service_arn]
  }

  statement {
    sid       = "ProvisionDefaultFrontendCluster"
    effect    = "Allow"
    actions   = ["ecs:CreateCluster"]
    resources = [local.frontend_cluster_arn]
  }

  statement {
    sid    = "ProvisionFrontendExpressDependencies"
    effect = "Allow"
    actions = [
      "ecs:AssociateGatewayWithCluster",
      "ecs:CreateGateway",
      "ecs:RegisterTaskDefinition",
      "ecs:TagResource",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "ReadFrontendServiceDeployments"
    effect = "Allow"

    actions = [
      "ecs:ListServiceDeployments",
      "ecs:DescribeServiceDeployments",
      "ecs:DescribeServiceRevisions",
    ]

    resources = [
      local.frontend_service_arn,
      local.frontend_service_deployment_arn,
      local.frontend_service_revision_arn,
    ]
  }
}

resource "aws_iam_policy" "github_actions_frontend" {
  name        = "${local.cd_role_name}-frontend-policy"
  description = "Frontend deployment permissions for ${var.project_name} ${var.deployment_environment}"
  policy      = data.aws_iam_policy_document.github_actions_frontend.json

  tags = merge(
    local.common_tags,
    {
      Name        = "${local.cd_role_name}-frontend-policy"
      Environment = var.deployment_environment
      Purpose     = "github-actions-frontend-cd"
    }
  )
}

resource "aws_iam_role_policy_attachment" "github_actions_frontend" {
  role       = aws_iam_role.github_actions_cd.name
  policy_arn = aws_iam_policy.github_actions_frontend.arn
}
