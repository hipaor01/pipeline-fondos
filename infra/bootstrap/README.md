# Bootstrap de Terraform

Este root module gestiona la base necesaria antes de ejecutar la pipeline de
CD:

- el bucket S3 utilizado como backend remoto;
- la consulta del proveedor OIDC de GitHub Actions ya existente en la cuenta;
- el rol y la política de despliegue del entorno `dev`;
- las permissions boundaries de la API y de captura.

El bucket de estado tiene:

- versionado para recuperar estados anteriores;
- cifrado SSE-S3 (`AES256`);
- acceso público bloqueado;
- propiedad de objetos forzada a la cuenta propietaria;
- una política que rechaza conexiones sin TLS;
- protección de Terraform frente al borrado accidental.

No se crea una tabla DynamoDB. Los root modules que usen este bucket deben
activar el bloqueo nativo del backend S3 con `use_lockfile = true`.

## Estado del bootstrap

En esta cuenta el bucket ya se creó inicialmente con estado local y ese estado
se migró después al propio bucket S3. `backend.tf` presupone por tanto que el
bucket existe. Desde un checkout nuevo se inicializa así:

```bash
cd infra/bootstrap
terraform init \
  -backend-config="bucket=pipeline-fondos-terraform-state-065451207233"
```

El nombre predeterminado es
`pipeline-fondos-terraform-state-<aws-account-id>`. Se puede personalizar
copiando `terraform.tfvars.example` a `terraform.tfvars`.

La secuencia de creación local y `terraform init -migrate-state` solo debe
repetirse al preparar una cuenta AWS nueva, antes de añadir el backend S3.

## Acceso de GitHub Actions

El proveedor `token.actions.githubusercontent.com` es compartido por la cuenta
y ya existía antes de este código, por lo que Terraform lo consulta mediante un
data source y no intenta recrearlo.

La relación de confianza del rol exige:

- audience `sts.amazonaws.com`;
- el subject OIDC inmutable del repositorio `hipaor01/pipeline-fondos`;
- la rama exacta `main`.

El rol puede administrar el bucket de artefactos reservado, los estados de los
roots `dev`, la API y el frontend. También recibe políticas separadas para los
los estados de storage y captura, su único repositorio ECR y los recursos Lambda, Step Functions,
Scheduler, SQS y CloudWatch con nombres conocidos. Sobre el bucket documental
solo puede comprobar propiedad y configuración; son los roles de ejecución los
que pueden escribir bajo `raw/` y `manifests/`. El rol no puede modificar su
propia política. API Gateway no permite delimitar la creación inicial por
nombre, por lo que sus acciones se limitan al servicio API Gateway de
`eu-west-3`, pero no a un ID que todavía no existe.

La pipeline solo puede crear el rol de ejecución de Lambda si adjunta la
permissions boundary gestionada por este bootstrap. Aunque pueda modificar la
política inline de ese rol, sus permisos efectivos quedan limitados actualmente
a escribir en el grupo de logs de la Lambda. Cuando la API necesite Aurora o
Secrets Manager, la frontera se ampliará aquí mediante un `apply` manual.

Los cinco roles de captura también deben usar la boundary gestionada por el
bootstrap. Esta limita el máximo efectivo a los logs y prefijos S3 de captura,
la invocación de sus tres Lambdas, el inicio de su máquina de estados y el envío
a su DLQ. Para habilitar esos recursos hay que aplicar manualmente:

```bash
terraform plan \
  -var='capture_documents_bucket=NOMBRE-DEL-BUCKET-COMPROBADO' \
  -out=capture-bootstrap.tfplan
terraform apply capture-bootstrap.tfplan
```

El mismo nombre debe guardarse en la variable de repositorio
`CAPTURE_DOCUMENTS_BUCKET`. Usar otro hará que la inspección o el despliegue
fallen por diseño.

El bootstrap se aplica manualmente; la pipeline no debe aplicar el root que
gestiona su propia relación de confianza. `capture_documents_bucket` es
obligatorio; conviene conservarlo en un `terraform.tfvars` local no versionado
para que cada plan use explícitamente el mismo bucket:

```bash
terraform plan \
  -var='capture_documents_bucket=NOMBRE-DEL-BUCKET-COMPROBADO' \
  -out=bootstrap.tfplan
terraform apply bootstrap.tfplan
terraform output -raw github_actions_cd_role_arn
```

## Configuración de los entornos

Cada entorno utilizará una clave independiente. Por ejemplo, el backend de
`dev` tendrá una configuración equivalente a:

```hcl
terraform {
  backend "s3" {
    bucket       = "pipeline-fondos-terraform-state-123456789012"
    key          = "pipeline-fondos/dev/terraform.tfstate"
    region       = "eu-west-3"
    encrypt      = true
    use_lockfile = true
  }
}
```

El nombre real del bucket se obtiene con `terraform output` y no debe
duplicarse literalmente hasta que se conozca la cuenta de AWS de despliegue.
