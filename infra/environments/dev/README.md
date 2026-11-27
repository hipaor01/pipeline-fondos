# Entorno dev

Este root module configura el provider de AWS y despliega `modules/api` en el
entorno `dev`. Utiliza el bucket creado por `infra/bootstrap` como backend S3,
con bloqueo mediante lockfile.

## Despliegue mediante CD

El workflow orquestador `.github/workflows/deploy-backend-dev.yml` ejecuta
primero `.github/workflows/deploy-processing-dev.yml` y, solo después de que
termine correctamente el despliegue y las migraciones, invoca
`.github/workflows/deploy-api-dev.yml`. Este último se encarga de:

- ejecutar los tests y validaciones;
- aplicar el root `dev/artifacts`;
- construir y subir el ZIP versionado;
- proporcionar `lambda_package` a este root;
- leer del estado de procesamiento los ARN de Aurora y Secrets Manager;
- aplicar la infraestructura de la API y comprobar `/health` y `/gestoras`.

El frontend usa el root separado `dev/frontend` y el workflow
`.github/workflows/publish-frontend-dev.yml`. Este crea el repositorio ECR,
publica una imagen Linux ARM64 inmutable por commit y aplica el root
`dev/frontend-service` para desplegar su digest en ECS Express Mode. Los estados
separados evitan ciclos entre el registro, la imagen y el servicio.

La pipeline necesita que `infra/bootstrap` esté aplicado y que la variable de
repositorio `AWS_DEPLOY_ROLE_ARN` contenga el output
`github_actions_cd_role_arn`. El orquestador despliega `dev/processing` antes
de que este estado consuma sus outputs de base de datos.

Después de incorporar cambios en `infra/bootstrap/lambda_boundary.tf`, aplica
primero `infra/bootstrap` de forma administrativa. La permissions boundary debe
permitir Data API y Secrets Manager antes de desplegar la nueva Lambda del API.

## Uso local opcional

`terraform.tfvars.example` permite realizar un despliegue manual si ya existe
un ZIP en S3:

```bash
cp infra/environments/dev/terraform.tfvars.example \
  infra/environments/dev/terraform.tfvars
```

Sustituye todos los valores `REPLACE_...` del archivo copiado. Si el bucket de
artefactos tiene versionado, también puedes añadir `s3_object_version` dentro
de `lambda_package`.

## Inicialización y despliegue

El backend es parcial porque el nombre del bucket contiene el ID de la cuenta:

```bash
TF_STATE_BUCKET=$(terraform -chdir=infra/bootstrap output -raw state_bucket_name)

terraform -chdir=infra/environments/dev init \
  -backend-config="bucket=${TF_STATE_BUCKET}"
terraform -chdir=infra/environments/dev plan
terraform -chdir=infra/environments/dev apply
```

Tras el despliegue:

```bash
API_ENDPOINT=$(terraform -chdir=infra/environments/dev output -raw api_endpoint)
curl "${API_ENDPOINT}/health"
curl "${API_ENDPOINT}/gestoras?tamano_pagina=1"
```

No guardes credenciales ni secretos en `terraform.tfvars`; utiliza la cadena
de credenciales estándar de AWS y, para secretos de la aplicación, Secrets
Manager o Parameter Store.
