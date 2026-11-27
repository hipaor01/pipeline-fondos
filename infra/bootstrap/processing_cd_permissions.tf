# Permisos del rol de GitHub Actions para desplegar la capa de procesamiento y datos (P2):
# roots `dev/processing-registry` y `dev/processing`. Separado en su propio fichero y
# política, igual que el frontend, para no tocar los permisos de la API.
#
# PROPUESTA DE P2: bootstrap es de P3; revisar y aplicar a mano con
#   terraform -chdir=infra/bootstrap apply

locals {
  processing_prefix         = "${var.project_name}-${var.deployment_environment}"
  processing_function_names = ["${local.processing_prefix}-pdf-markdown", "${local.processing_prefix}-extraccion"]
  processing_account        = data.aws_caller_identity.current.account_id
  processing_arn_prefix     = "arn:aws:%s:${var.aws_region}:${data.aws_caller_identity.current.account_id}"

  processing_state_keys = [
    "${var.project_name}/${var.deployment_environment}/processing/terraform.tfstate",
    "${var.project_name}/${var.deployment_environment}/processing-registry/terraform.tfstate",
  ]

  processing_repository_arn = "${format(local.processing_arn_prefix, "ecr")}:repository/${local.processing_prefix}-processing"
  processing_cluster_id     = "${local.processing_prefix}-aurora"
  processing_cluster_arn    = "${format(local.processing_arn_prefix, "rds")}:cluster:${local.processing_cluster_id}"
  processing_role_arns      = [for f in local.processing_function_names : "arn:aws:iam::${local.processing_account}:role/${f}-exec"]
  processing_boundary_name  = "${local.processing_prefix}-processing-boundary"
  processing_function_arns  = [for f in local.processing_function_names : "${format(local.processing_arn_prefix, "lambda")}:function:${f}"]
  processing_queue_arns     = flatten([for f in local.processing_function_names : ["${format(local.processing_arn_prefix, "sqs")}:${f}", "${format(local.processing_arn_prefix, "sqs")}:${f}-dlq"]])
  processing_log_group_arns = flatten([for f in local.processing_function_names : ["${format(local.processing_arn_prefix, "logs")}:log-group:/aws/lambda/${f}", "${format(local.processing_arn_prefix, "logs")}:log-group:/aws/lambda/${f}:*"]])
  processing_secret_arn     = "${format(local.processing_arn_prefix, "secretsmanager")}:secret:rds!cluster-*"
}

# ------------------------------------------------------------------ boundary de los roles de ejecución

data "aws_iam_policy_document" "processing_boundary" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [for f in local.processing_function_names : "${format(local.processing_arn_prefix, "logs")}:log-group:/aws/lambda/${f}:*"]
  }

  statement {
    sid       = "Queues"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
    resources = local.processing_queue_arns
  }

  statement {
    sid       = "Documents"
    actions   = ["s3:GetObject", "s3:GetObjectVersion", "s3:PutObject"]
    resources = ["arn:aws:s3:::${var.capture_documents_bucket}/raw/*", "arn:aws:s3:::${var.capture_documents_bucket}/processed/*"]
  }

  statement {
    sid       = "ListDocuments"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.capture_documents_bucket}"]
  }

  statement {
    sid       = "Bedrock"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:*::foundation-model/*", "arn:aws:bedrock:::foundation-model/*", "${format(local.processing_arn_prefix, "bedrock")}:inference-profile/*"]
  }

  statement {
    sid       = "DataApi"
    actions   = ["rds-data:ExecuteStatement", "rds-data:BeginTransaction", "rds-data:CommitTransaction", "rds-data:RollbackTransaction"]
    resources = [local.processing_cluster_arn]
  }

  statement {
    sid       = "DatabaseSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.processing_secret_arn]
  }
}

resource "aws_iam_policy" "processing_boundary" {
  name        = local.processing_boundary_name
  description = "Permisos máximos de los roles de las Lambdas de procesamiento de ${local.processing_prefix}"
  policy      = data.aws_iam_policy_document.processing_boundary.json

  tags = merge(local.common_tags, { Name = local.processing_boundary_name, Purpose = "permissions-boundary" })
}

# ------------------------------------------------------------------ permisos de despliegue

data "aws_iam_policy_document" "github_actions_processing" {
  statement {
    sid       = "ProcessingState"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = flatten([for k in local.processing_state_keys : ["${aws_s3_bucket.terraform_state.arn}/${k}", "${aws_s3_bucket.terraform_state.arn}/${k}.tflock"]])
  }

  statement {
    sid       = "ProcessingStateLocks"
    actions   = ["s3:DeleteObject"]
    resources = [for k in local.processing_state_keys : "${aws_s3_bucket.terraform_state.arn}/${k}.tflock"]
  }

  statement {
    sid = "ProcessingRepository"
    actions = [
      "ecr:CreateRepository", "ecr:DeleteRepository", "ecr:DescribeRepositories", "ecr:DescribeImages",
      "ecr:GetLifecyclePolicy", "ecr:PutLifecyclePolicy", "ecr:DeleteLifecyclePolicy",
      "ecr:GetRepositoryPolicy", "ecr:SetRepositoryPolicy", "ecr:DeleteRepositoryPolicy",
      "ecr:PutImageScanningConfiguration", "ecr:PutImageTagMutability",
      "ecr:ListTagsForResource", "ecr:TagResource", "ecr:UntagResource",
      "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
      "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage",
    ]
    resources = [local.processing_repository_arn]
  }

  statement {
    sid = "ProcessingLambdas"
    actions = [
      "lambda:CreateFunction", "lambda:DeleteFunction", "lambda:GetFunction", "lambda:GetFunctionConfiguration",
      "lambda:GetFunctionCodeSigningConfig", "lambda:ListVersionsByFunction", "lambda:ListTags",
      "lambda:TagResource", "lambda:UntagResource", "lambda:UpdateFunctionCode", "lambda:UpdateFunctionConfiguration",
    ]
    resources = local.processing_function_arns
  }

  statement {
    sid       = "CreateEventSourceMappings"
    actions   = ["lambda:CreateEventSourceMapping"]
    resources = ["*"]

    condition {
      test     = "ArnLike"
      variable = "lambda:FunctionArn"
      values   = local.processing_function_arns
    }
  }

  statement {
    sid = "ManageEventSourceMappings"
    actions = [
      "lambda:GetEventSourceMapping", "lambda:UpdateEventSourceMapping", "lambda:DeleteEventSourceMapping",
      "lambda:TagResource", "lambda:UntagResource", "lambda:ListTags",
    ]
    resources = ["${format(local.processing_arn_prefix, "lambda")}:event-source-mapping:*"]
  }

  statement {
    sid       = "ListEventSourceMappings"
    actions   = ["lambda:ListEventSourceMappings"]
    resources = ["*"]
  }

  statement {
    sid       = "CreateProcessingRolesWithBoundary"
    actions   = ["iam:CreateRole", "iam:PutRolePermissionsBoundary"]
    resources = local.processing_role_arns

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.processing_boundary.arn]
    }
  }

  statement {
    sid = "ManageProcessingRoles"
    actions = [
      "iam:DeleteRole", "iam:GetRole", "iam:GetRolePolicy", "iam:PutRolePolicy", "iam:DeleteRolePolicy",
      "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole", "iam:ListRolePolicies",
      "iam:TagRole", "iam:UntagRole", "iam:UpdateAssumeRolePolicy", "iam:UpdateRoleDescription",
    ]
    resources = local.processing_role_arns
  }

  statement {
    sid       = "PassProcessingRoles"
    actions   = ["iam:PassRole"]
    resources = local.processing_role_arns

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }

  statement {
    sid = "ProcessingQueues"
    actions = [
      "sqs:CreateQueue", "sqs:DeleteQueue", "sqs:GetQueueAttributes", "sqs:SetQueueAttributes",
      "sqs:ListQueueTags", "sqs:TagQueue", "sqs:UntagQueue", "sqs:ListDeadLetterSourceQueues",
    ]
    resources = local.processing_queue_arns
  }

  # P2 gestiona la configuración completa de notificaciones del bucket de documentos.
  statement {
    sid       = "DocumentBucketNotifications"
    actions   = ["s3:GetBucketNotification", "s3:PutBucketNotification", "s3:GetBucketVersioning"]
    resources = ["arn:aws:s3:::${var.capture_documents_bucket}"]
  }

  statement {
    sid = "ProcessingLogGroups"
    actions = [
      "logs:CreateLogGroup", "logs:DeleteLogGroup", "logs:PutRetentionPolicy", "logs:DeleteRetentionPolicy",
      "logs:ListTagsForResource", "logs:ListTagsLogGroup", "logs:TagResource", "logs:UntagResource",
    ]
    resources = local.processing_log_group_arns
  }

}

# Segunda política: una gestionada admite como máximo 6.144 caracteres.
data "aws_iam_policy_document" "github_actions_processing_database" {
  statement {
    sid = "AuroraCluster"
    actions = [
      "rds:CreateDBCluster", "rds:DeleteDBCluster", "rds:ModifyDBCluster", "rds:DescribeDBClusters",
      "rds:CreateDBInstance", "rds:DeleteDBInstance", "rds:ModifyDBInstance", "rds:DescribeDBInstances",
      "rds:CreateDBSubnetGroup", "rds:DeleteDBSubnetGroup", "rds:ModifyDBSubnetGroup", "rds:DescribeDBSubnetGroups",
      "rds:EnableHttpEndpoint", "rds:DisableHttpEndpoint",
      "rds:AddTagsToResource", "rds:RemoveTagsFromResource", "rds:ListTagsForResource",
    ]
    resources = [
      local.processing_cluster_arn,
      "${format(local.processing_arn_prefix, "rds")}:db:${local.processing_cluster_id}-*",
      "${format(local.processing_arn_prefix, "rds")}:subgrp:${local.processing_cluster_id}",
      "${format(local.processing_arn_prefix, "rds")}:cluster-pg:default.*",
      "${format(local.processing_arn_prefix, "rds")}:pg:default.*",
      "${format(local.processing_arn_prefix, "rds")}:og:default*",
      "${format(local.processing_arn_prefix, "rds")}:secgrp:*",
    ]
  }

  statement {
    sid       = "DescribeRdsEngines"
    actions   = ["rds:DescribeDBEngineVersions", "rds:DescribeOrderableDBInstanceOptions"]
    resources = ["*"]
  }

  statement {
    sid       = "RdsManagedSecret"
    actions   = ["secretsmanager:CreateSecret", "secretsmanager:TagResource", "secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue"]
    resources = [local.processing_secret_arn]
  }

  statement {
    sid       = "DescribeManagedDatabaseKeys"
    actions   = ["kms:DescribeKey"]
    resources = ["*"]
  }

  statement {
    sid       = "RunMigrations"
    actions   = ["rds-data:ExecuteStatement", "rds-data:BeginTransaction", "rds-data:CommitTransaction", "rds-data:RollbackTransaction"]
    resources = [local.processing_cluster_arn]
  }

  statement {
    sid       = "RdsServiceLinkedRole"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["arn:aws:iam::${local.processing_account}:role/aws-service-role/rds.amazonaws.com/*"]

    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values   = ["rds.amazonaws.com"]
    }
  }

  statement {
    sid       = "DescribeNetwork"
    actions   = ["ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups", "ec2:DescribeNetworkInterfaces", "ec2:DescribeAvailabilityZones", "ec2:DescribeVpcAttribute"]
    resources = ["*"]
  }

  statement {
    sid       = "ManageAuroraSecurityGroup"
    actions   = ["ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup", "ec2:RevokeSecurityGroupEgress", "ec2:CreateTags", "ec2:DeleteTags"]
    resources = ["arn:aws:ec2:${var.aws_region}:${local.processing_account}:security-group/*", "arn:aws:ec2:${var.aws_region}:${local.processing_account}:vpc/*"]
  }
}

resource "aws_iam_policy" "github_actions_processing" {
  name        = "${local.cd_role_name}-processing-policy"
  description = "Permisos de despliegue de la capa de procesamiento de ${local.processing_prefix}"
  policy      = data.aws_iam_policy_document.github_actions_processing.json

  tags = merge(local.common_tags, { Name = "${local.cd_role_name}-processing-policy", Purpose = "github-actions-cd" })
}

resource "aws_iam_role_policy_attachment" "github_actions_processing" {
  role       = aws_iam_role.github_actions_cd.name
  policy_arn = aws_iam_policy.github_actions_processing.arn
}

resource "aws_iam_policy" "github_actions_processing_database" {
  name        = "${local.cd_role_name}-processing-database-policy"
  description = "Permisos de despliegue de Aurora de ${local.processing_prefix}"
  policy      = data.aws_iam_policy_document.github_actions_processing_database.json

  tags = merge(local.common_tags, { Name = "${local.cd_role_name}-processing-database-policy", Purpose = "github-actions-cd" })
}

resource "aws_iam_role_policy_attachment" "github_actions_processing_database" {
  role       = aws_iam_role.github_actions_cd.name
  policy_arn = aws_iam_policy.github_actions_processing_database.arn
}
