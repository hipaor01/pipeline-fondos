# terraform -chdir=infra/modules/api init -backend=false && terraform -chdir=infra/modules/api test
# Usa un proveedor simulado: no necesita credenciales de AWS.

mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }

  mock_resource "aws_iam_role" {
    defaults = {
      id  = "rol-api"
      arn = "arn:aws:iam::123456789012:role/rol-api"
    }
  }

  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:eu-west-3:123456789012:log-group:grupo" }
  }

  mock_resource "aws_lambda_function" {
    defaults = {
      arn        = "arn:aws:lambda:eu-west-3:123456789012:function:api"
      invoke_arn = "arn:aws:apigateway:eu-west-3:lambda:path/api"
    }
  }

  mock_resource "aws_apigatewayv2_api" {
    defaults = {
      id            = "api-id"
      api_endpoint  = "https://api.example.test"
      execution_arn = "arn:aws:execute-api:eu-west-3:123456789012:api-id"
    }
  }
}

variables {
  environment = "test"
  lambda_package = {
    s3_bucket        = "bucket-artefactos"
    s3_key           = "api/commit/api.zip"
    source_code_hash = "47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU="
  }
  lambda_permissions_boundary_arn = "arn:aws:iam::123456789012:policy/api-boundary"
  database_cluster_arn            = "arn:aws:rds:eu-west-3:123456789012:cluster:fondos"
  database_secret_arn             = "arn:aws:secretsmanager:eu-west-3:123456789012:secret:rds!cluster-fondos"
  database_name                   = "fondos"
  lambda_environment_variables = {
    PERSONALIZADA      = "conservada"
    REPOSITORIO_FONDOS = "memoria"
    DB_NAME            = "incorrecta"
  }
}

run "configura_aurora_en_la_lambda" {
  command = plan

  assert {
    condition     = aws_lambda_function.api.environment[0].variables["REPOSITORIO_FONDOS"] == "aurora"
    error_message = "La Lambda debe seleccionar explícitamente el repositorio Aurora."
  }

  assert {
    condition     = aws_lambda_function.api.environment[0].variables["DB_CLUSTER_ARN"] == var.database_cluster_arn
    error_message = "La Lambda debe recibir el ARN del clúster."
  }

  assert {
    condition     = aws_lambda_function.api.environment[0].variables["DB_SECRET_ARN"] == var.database_secret_arn
    error_message = "La Lambda debe recibir el ARN del secreto."
  }

  assert {
    condition     = aws_lambda_function.api.environment[0].variables["DB_NAME"] == "fondos"
    error_message = "La configuración estructural debe prevalecer sobre el mapa personalizado."
  }

  assert {
    condition     = aws_lambda_function.api.environment[0].variables["PERSONALIZADA"] == "conservada"
    error_message = "Las variables de entorno personalizadas deben conservarse."
  }
}

run "limita_los_permisos_a_los_recursos_de_aurora" {
  command = plan

  assert {
    condition     = contains(flatten([for statement in data.aws_iam_policy_document.lambda_database.statement : statement.actions]), "rds-data:ExecuteStatement")
    error_message = "El rol debe permitir ExecuteStatement."
  }

  assert {
    condition     = contains(flatten([for statement in data.aws_iam_policy_document.lambda_database.statement : statement.resources]), var.database_cluster_arn)
    error_message = "El permiso Data API debe limitarse al clúster configurado."
  }

  assert {
    condition     = contains(flatten([for statement in data.aws_iam_policy_document.lambda_database.statement : statement.actions]), "secretsmanager:GetSecretValue")
    error_message = "El rol debe poder leer las credenciales de Aurora."
  }

  assert {
    condition     = contains(flatten([for statement in data.aws_iam_policy_document.lambda_database.statement : statement.resources]), var.database_secret_arn)
    error_message = "El permiso de Secrets Manager debe limitarse al secreto configurado."
  }
}
