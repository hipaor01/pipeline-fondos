# Módulo de la API

Este módulo desplegará la aplicación FastAPI como una función Lambda detrás de
API Gateway HTTP API v2. El enrutado será un proxy `$default`: API Gateway
entregará la petición a Mangum y FastAPI resolverá la ruta correspondiente.

El módulo no construye código ni crea el bucket de artefactos. Recibe un ZIP
inmutable, generado para Linux y para la arquitectura seleccionada, mediante
`lambda_package`. El bucket de artefactos debe estar en la misma región que la
función Lambda.

## Interfaz inicial

Ejemplo de uso desde un entorno:

```hcl
module "api" {
  source = "../../modules/api"

  project_name = "pipeline-fondos"
  environment  = "dev"

  lambda_package = {
    s3_bucket         = "pipeline-fondos-artifacts-123456789012"
    s3_key            = "api/0123456789abcdef.zip"
    s3_object_version = "opcional-si-el-bucket-tiene-versionado"
    source_code_hash  = "47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU=" # Ejemplo de formato
  }

  lambda_permissions_boundary_arn = "arn:aws:iam::123456789012:policy/pipeline-fondos-dev-lambda-boundary"

  cors_configuration = {
    allow_origins = ["http://localhost:3000"]
  }

  additional_tags = {
    Owner = "persona-3"
  }
}
```

`source_code_hash` debe ser el SHA-256 binario del ZIP codificado en Base64,
no el ETag del objeto S3.

## Recursos implementados

- dos grupos de CloudWatch Logs con retención explícita;
- rol IAM de ejecución con privilegios mínimos;
- función Lambda `python3.14` y handler `api.lambda_handler.handler`;
- HTTP API con integración Lambda proxy payload v2;
- ruta y stage `$default`;
- permiso de invocación desde API Gateway.

El stage genera access logs JSON e incluye `$context.integrationErrorMessage`
para diagnosticar errores de integración que API Gateway devuelve como 500.
