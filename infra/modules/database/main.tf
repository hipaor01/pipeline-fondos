# Aurora PostgreSQL Serverless v2 con RDS Data API (contrato C4).
#
# - Acceso solo por Data API (HTTPS + IAM + Secrets Manager): las Lambdas no
#   necesitan VPC y el grupo de seguridad no abre ningún puerto.
# - La contraseña la genera y rota RDS en Secrets Manager (manage_master_user_password).
# - min_capacity = 0: el clúster se pausa tras `seconds_until_auto_pause` sin
#   actividad (PostgreSQL 16.3+). La primera llamada tras la pausa tarda ~15 s;
#   el ejecutor Data API lo reintenta.

locals {
  resource_prefix    = "${var.project_name}-${var.environment}"
  cluster_identifier = "${local.resource_prefix}-aurora"

  common_tags = merge(
    var.additional_tags,
    {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
      Component   = "database"
    }
  )
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_rds_engine_version" "postgresql" {
  engine  = "aurora-postgresql"
  version = var.engine_major_version
  latest  = true
}

resource "aws_db_subnet_group" "this" {
  name       = "${local.resource_prefix}-aurora"
  subnet_ids = data.aws_subnets.default.ids

  tags = merge(local.common_tags, { Name = "${local.resource_prefix}-aurora" })
}

# Sin reglas de entrada: nadie se conecta por red, solo por Data API.
resource "aws_security_group" "aurora" {
  name        = "${local.resource_prefix}-aurora"
  description = "Aurora ${local.resource_prefix}: sin acceso de red, solo RDS Data API"
  vpc_id      = data.aws_vpc.default.id

  tags = merge(local.common_tags, { Name = "${local.resource_prefix}-aurora" })
}

resource "aws_rds_cluster" "this" {
  cluster_identifier = local.cluster_identifier
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = data.aws_rds_engine_version.postgresql.version
  database_name      = var.database_name
  master_username    = var.master_username

  manage_master_user_password = true
  enable_http_endpoint        = true
  storage_encrypted           = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.aurora.id]

  serverlessv2_scaling_configuration {
    min_capacity             = var.min_capacity
    max_capacity             = var.max_capacity
    seconds_until_auto_pause = var.min_capacity == 0 ? var.seconds_until_auto_pause : null
  }

  backup_retention_period   = var.backup_retention_days
  copy_tags_to_snapshot     = true
  deletion_protection       = var.deletion_protection
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${local.cluster_identifier}-final"
  apply_immediately         = true

  tags = merge(local.common_tags, { Name = local.cluster_identifier })

  lifecycle {
    # Las versiones menores las actualiza AWS; no se fuerza un cambio en cada plan.
    ignore_changes = [engine_version]
  }
}

resource "aws_rds_cluster_instance" "writer" {
  identifier          = "${local.cluster_identifier}-1"
  cluster_identifier  = aws_rds_cluster.this.id
  instance_class      = "db.serverless"
  engine              = aws_rds_cluster.this.engine
  engine_version      = aws_rds_cluster.this.engine_version
  publicly_accessible = false

  auto_minor_version_upgrade = true

  tags = merge(local.common_tags, { Name = "${local.cluster_identifier}-1" })

  lifecycle {
    ignore_changes = [engine_version]
  }
}
