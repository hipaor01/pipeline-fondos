# Almacenamiento de documentos P1

Esta raíz es independiente de captura, API y artefactos. Por defecto solo
referencia un bucket existente: no lo importa ni comprueba o modifica su
configuración. `create_bucket=true` crea y administra uno nuevo con versionado,
cifrado SSE-S3 y bloqueo de acceso público; no crea políticas, reglas de
caducidad ni notificaciones. El nombre debe ser globalmente único y el bucket
de documentos debe ser distinto de los buckets de estado y artefactos.

Antes de usar un bucket existente, verificar su propietario, región,
versionado `Enabled`, cifrado y privacidad efectiva, incluyendo políticas,
ACL y controles de cuenta. Inventariar sus notificaciones y el estado que lo
administra. No importarlo ni gestionar sus recursos desde dos estados. La
región de salida es la configurada, no una comprobación del bucket existente.
P2 debe coordinar la configuración completa de notificaciones.

Comprobación inicial de un bucket existente en la cuenta activa:

```bash
export PF_REGION=eu-west-3
export PF_BUCKET='NOMBRE-DEL-BUCKET-EXISTENTE'
export PF_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
aws s3api head-bucket --bucket "$PF_BUCKET" --expected-bucket-owner "$PF_ACCOUNT"
aws s3api get-bucket-location --bucket "$PF_BUCKET" --expected-bucket-owner "$PF_ACCOUNT"
aws s3api get-bucket-versioning --bucket "$PF_BUCKET" --expected-bucket-owner "$PF_ACCOUNT"
aws s3api get-bucket-encryption --bucket "$PF_BUCKET" --expected-bucket-owner "$PF_ACCOUNT"
aws s3api get-public-access-block --bucket "$PF_BUCKET" --expected-bucket-owner "$PF_ACCOUNT"
aws s3api get-bucket-notification-configuration --bucket "$PF_BUCKET" --expected-bucket-owner "$PF_ACCOUNT"
```

La inspección no modifica el bucket ni demuestra por sí sola todas las políticas
y vías de acceso. Si falta alguna configuración o aparece un error, investigarlo
antes de usar el bucket; no aplicar cambios sobre recursos de otra persona.

Por defecto Terraform usa estado local en este directorio. Conservarlo y
respaldarlo; antes de compartirlo, acordar y migrar a un backend remoto con una
clave independiente. Nunca inicializar otro estado para administrar el mismo
bucket. No guardar estado ni credenciales en Git.

```bash
terraform -chdir=infra/environments/dev/storage init
terraform -chdir=infra/environments/dev/storage validate
terraform -chdir=infra/environments/dev/storage test
terraform -chdir=infra/environments/dev/storage plan \
  -var='bucket_name=NOMBRE-DEL-BUCKET' -var='create_bucket=true'
```

Para un bucket existente omitir `create_bucket=true`. Revisar el plan y la
cuenta antes de aplicar. Para conectar captura, pasar el output `bucket_name`
como `documents_bucket`. Un bucket recién versionado puede tardar en propagar
el cambio; comprobar la configuración efectiva antes de subir documentos.
Cambiar de modo, nombre o estado puede planificar destrucciones: `prevent_destroy`
protege el recurso mientras permanezca en la configuración, y `force_destroy`
está desactivado; revisar siempre el plan y conservar los datos y el estado.
Las pruebas simuladas no verifican seguridad ni configuración reales en AWS.

## Evidencia de prueba personal

El 25-11-2026 se planificó la referencia a un bucket existente sin cambios y la
creación de un bucket temporal con cuatro recursos. Se creó en `eu-west-3`,
se comprobaron con AWS CLI versionado `Enabled`, cifrado AES-256 y los cuatro
bloqueos públicos; tras comprobar que no contenía versiones ni marcadores, se
eliminó el bucket temporal. Esta prueba no verifica el bucket compartido.
