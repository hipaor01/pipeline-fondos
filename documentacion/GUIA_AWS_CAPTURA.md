# Guía AWS: captura de documentos de fondos

Esta guía explica cómo está organizada la captura P1, qué decisiones se han tomado y cómo preparar **un bucket de pruebas propio** con AWS CLI para ejecutar el scraper actual. No es un despliegue completo del proyecto: la conversión, P2 y su cola siguen sin conectarse. La ejecución programada de P1 se ha probado en la cuenta personal y está documentada en [AUTOMATIZACION_P1.md](AUTOMATIZACION_P1.md).

## Estado comprobado

El 23 de noviembre de 2026 se inspeccionó una cuenta personal para reproducir y probar la configuración, distinta de la cuenta de la integración Terraform del compañero mencionada en los workflows del repositorio. **Antes de crear el bucket de prueba** se obtuvo una lista vacía de buckets S3 y, en `eu-west-3`, listas vacías de funciones Lambda, máquinas de Step Functions, colas SQS, schedules, repositorios ECR, API HTTP, clústeres ECS y clústeres Aurora. La cuenta sí tenía roles IAM ajenos al proyecto; no se inspeccionó ni alteró su contenido. No se puede concluir que otras regiones o servicios estén vacíos ni extraer conclusiones sobre la cuenta del compañero.

El repositorio sí contiene Terraform para el backend de estado, la API, el bucket de artefactos y el frontend de **otro entorno**. Sus identificadores de cuenta y configuración de GitHub no deben copiarse tal cual a una cuenta nueva. No hay módulos implementados para las Lambdas de captura, Scheduler, Step Functions, SQS de procesamiento o el bucket de documentos. La arquitectura de `arquitectura_aws_pipeline_fondos.*` es una propuesta, no evidencia de despliegue.

En una comprobación de lectura, el scraper encontró 24 enlaces de fondos en Bestinver. La web puede cambiar. Posteriormente se creó un bucket S3 de prueba en la cuenta personal y se realizaron las dos capturas descritas a continuación; no se configuraron notificaciones ni se tocaron recursos de la cuenta del compañero.

### Resultado de la prueba real del 23 de noviembre

El bucket de prueba se creó en `eu-west-3`, con acceso público bloqueado, cifrado `AES256` y versionado activado. Se esperaron 15 minutos tras activar el versionado antes de escribir objetos. Se comprobó la configuración efectiva y se mantuvo el bucket para inspección.

| Ejecución | Resultado | Subidas | Ausencias | Fallos |
| --- | --- | --- | --- | --- |
| `p1-aws-prueba-20261123-1` | Parcial | 21 KID y 15 fichas | 11 | 1 PDF rechazado por la validación estricta |
| `p1-aws-prueba-20261123-2` | Completa | 22 KID y 15 fichas | 11 | 0 |

El KID de Bestinver Consumo Global tenía una tabla de referencias dañada. El modo estricto de `pypdf` lo rechazó, pero el modo recuperable y `pdfinfo` identificaron tres páginas; `pypdf` también extrajo texto de cada página. Se cambió la validación para aceptar documentos recuperables y se mantuvieron los rechazos de respuestas vacías, HTML y PDF ilegibles. Esto no garantiza la corrección de la extracción que realice P2.

En ambas ejecuciones se leyó desde S3 **cada versión indicada en su manifiesto** y se compararon los bytes, su SHA-256, tipo de contenido, metadatos y `correlation-id`. Los 36 documentos presentes en ambas tenían el mismo hash y `VersionId` distinto. En total quedaron 37 claves PDF con 73 versiones físicas. La segunda ejecución incorporó el KID que había fallado en la primera. Esta prueba confirma el comportamiento de versionado y trazabilidad observado, **no** la deduplicación lógica, la integración con eventos ni la concurrencia en AWS.

El mismo día se probó Azvalor en el mismo bucket: se subieron 11 KID y 10 fichas con un manifiesto completo y se verificaron las 21 versiones y sus hashes. La página de Azvalor Capital FI no enlazaba una ficha. El análisis de la fuente y sus clases está en [CAPTURA_AZVALOR.md](CAPTURA_AZVALOR.md).

También se probó Cobas AM: se subieron 22 KID y 22 fichas de siete productos y sus clases, con un manifiesto completo. Se comprobaron las 44 versiones, hashes y metadatos y se encontró en el texto de cada uno de los 22 KID el ISIN identificado en su bloque de la web. Véase [CAPTURA_COBAS.md](CAPTURA_COBAS.md).

## Diseño y decisiones

```text
Hoy, ejecutado localmente:
  Bestinver / Azvalor / Cobas → scrapers Python → S3 versionado
                               ├─ raw/bestinver/FECHA/*_kid.pdf
                               ├─ raw/bestinver/FECHA/*_ficha_fondo.pdf
                               └─ manifests/bestinver/FECHA/.../*.json

Futuro, todavía no implementado:
  Scheduler → Step Functions → scrapers → S3 → SQS → procesamiento P2 → base de datos
```

- **Ámbito:** hay scrapers para Bestinver, Azvalor y Cobas. La región prevista para el proyecto es `eu-west-3`; el día de las carpetas se calcula en `Europe/Madrid` y el instante de descarga se registra en UTC.
- **Bucket de documentos:** separado del bucket que Terraform utiliza para su estado y del bucket de artefactos de despliegue. Su nombre se pasa con `--bucket`. Debe ser privado, estar cifrado y tener el versionado activado. La guía de abajo configura esto para una prueba; no lo añade al estado de Terraform.
- **Claves:** `raw/{gestora}/{AAAAMMDD}/{slug}_{tipo}.pdf`, con tipos `kid` y `ficha_fondo`. `raw/` y `manifests/` son prefijos de objetos, no carpetas que haya que crear previamente. La salida histórica `bestinver/..._datos_fundamentales.pdf` no se migra automáticamente.
- **Metadatos de cada PDF:** `gestora`, `tipo-documento`, `url-origen`, `fecha-descarga-utc`, `sha256` y `correlation-id`, además de `Content-Type: application/pdf`. El hash corresponde a los bytes descargados. Las subidas y sus versiones se registran en el manifiesto.
- **Trazabilidad y errores:** el scraper acepta `--correlation-id` o genera uno. El manifiesto JSON se guarda fuera de `raw/`, por intento, con estado, subidas, ausencias y fallos. El segmento de ejecución en la clave del manifiesto es un hash del identificador de correlación; el identificador original aparece en el JSON.
- **Repeticiones:** se puede volver a subir la misma clave y contenido, generando otra versión y potencialmente otro evento. P1 calcula el hash pero **no deduplica globalmente**; se propone que P2 imponga la unicidad lógica de forma transaccional y conserve las procedencias. P2 aún no está implementado.
- **Fichas y eventos futuros:** se propone que P2 procese solo claves terminadas en `_kid.pdf`. No hay notificaciones S3 ni colas configuradas por estos comandos. La configuración de notificaciones es única por bucket y debe tener un solo propietario: reemplazarla sin integrar las reglas existentes puede eliminarlas.
- **Limitación del manifiesto:** no es una transacción con S3. Una interrupción o un fallo al guardar el manifiesto puede dejar PDFs sin un registro final; si una subida devuelve un error, su resultado puede ser incierto. Hay que conciliar los objetos y sus versiones con los logs antes de reprocesar.

La propuesta detallada del contrato está en [C1_PROPUESTA.md](../contracts/C1_PROPUESTA.md).

## Requisitos

- AWS CLI v2 con una sesión autenticada y permisos para crear y configurar un bucket S3 y gestionar sus objetos. Preferir una identidad de trabajo con privilegios adecuados frente al uso cotidiano de la cuenta raíz.
- `uv`, Python 3.14 y acceso a Internet. Ejecutar los comandos Python desde la raíz del repositorio.
- Una cuenta de pruebas en la que esté permitido crear recursos y asumir los costes de almacenamiento y peticiones. Las versiones antiguas y manifiestos también ocupan espacio.
- La guía asume `eu-west-3`; la creación de buckets en `us-east-1` requiere una variante del comando AWS y no está cubierta aquí.

## 1. Identificar la cuenta y elegir un nombre

Estos comandos muestran la identidad activa. Comprobar que es la cuenta deseada **antes de crear nada**. El sufijo aleatorio reduce conflictos de nombres S3 globales. Conservar `PF_BUCKET` para los pasos siguientes; si el nombre ya existe, generar otro y volver a intentarlo.

```bash
aws sts get-caller-identity
export PF_REGION=eu-west-3
export PF_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export PF_SUFFIX="$(python3 -c 'import uuid; print(uuid.uuid4().hex[:10])')"
export PF_BUCKET="pipeline-fondos-p1-${PF_ACCOUNT_ID}-${PF_SUFFIX}"
printf 'Cuenta: %s\nRegión: %s\nBucket nuevo: %s\n' "$PF_ACCOUNT_ID" "$PF_REGION" "$PF_BUCKET"
```

Si se quiere reutilizar un bucket existente, inspeccionarlo primero: propiedad, región, objetos, versionado, cifrado, acceso público, políticas y **notificaciones existentes**. No ejecutar los comandos de creación o configuración siguientes sobre un bucket compartido sin revisar su efecto; el comando de notificaciones reemplaza la configuración completa. No asumir que `curso-miax-pipeline-fondos` pertenece a la cuenta activa.

## 2. Crear y configurar el bucket de prueba

```bash
aws s3api create-bucket \
  --bucket "$PF_BUCKET" \
  --region "$PF_REGION" \
  --create-bucket-configuration "LocationConstraint=$PF_REGION"

aws s3api put-public-access-block \
  --bucket "$PF_BUCKET" \
  --region "$PF_REGION" \
  --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'

aws s3api put-bucket-encryption \
  --bucket "$PF_BUCKET" \
  --region "$PF_REGION" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

aws s3api put-bucket-versioning \
  --bucket "$PF_BUCKET" \
  --region "$PF_REGION" \
  --versioning-configuration Status=Enabled
```

Tras activar por primera vez el versionado, **esperar 15 minutos antes de subir o borrar objetos**, aunque `get-bucket-versioning` ya devuelva `Enabled`: [AWS explica el periodo de propagación](https://docs.aws.amazon.com/AmazonS3/latest/userguide/manage-versioning-examples.html).

Comprobar la configuración efectiva:

```bash
aws s3api get-bucket-location --bucket "$PF_BUCKET"
aws s3api get-bucket-versioning --bucket "$PF_BUCKET" --region "$PF_REGION"
aws s3api get-public-access-block --bucket "$PF_BUCKET" --region "$PF_REGION"
aws s3api get-bucket-encryption --bucket "$PF_BUCKET" --region "$PF_REGION"
aws s3api get-bucket-notification-configuration --bucket "$PF_BUCKET" --region "$PF_REGION"
```

El versionado debe aparecer como `Enabled`, los cuatro controles de acceso público como `true` y el cifrado como `AES256`. Para un bucket recién creado, la configuración de notificaciones estará vacía salvo que se haya añadido alguna después.

## 3. Ejecutar y comprobar la captura

La CLI actual **recorre todos los fondos descubiertos**, no un solo PDF. Descargará KID y fichas y escribirá objetos y un manifiesto en el bucket indicado. Ejecutarla solo después de terminar el paso anterior y la espera:

```bash
uv sync --locked --group scraping
AWS_REGION="$PF_REGION" AWS_DEFAULT_REGION="$PF_REGION" \
  uv run --locked --group scraping python webscrapper/descargar_kids_bestinver.py \
  --bucket "$PF_BUCKET" --correlation-id prueba-bestinver-01
```

El script devuelve código `0` para una ejecución completa y distinto de cero para fallos o si no se ha subido ningún documento. Los documentos no publicados se informan como ausentes. Una subida sin `VersionId` se registra como fallo; el chequeo previo exige permiso `s3:GetBucketVersioning`. En macOS y Linux la variable `AWS_DEFAULT_REGION` ayuda a boto3 a seleccionar la región para esta ejecución.

Listar resultados y versiones:

```bash
aws s3api list-objects-v2 --bucket "$PF_BUCKET" --prefix raw/bestinver/ --region "$PF_REGION"
aws s3api list-objects-v2 --bucket "$PF_BUCKET" --prefix manifests/bestinver/ --region "$PF_REGION"
aws s3api list-object-versions --bucket "$PF_BUCKET" --prefix raw/bestinver/ --region "$PF_REGION"
```

Elegir una clave y su `VersionId` de la salida anterior y verificar la **versión exacta**. Sustituir los valores de ejemplo por los obtenidos; el `head-object` muestra `ContentType`, metadatos y versión. Para comprobar el SHA-256, descargar esa misma versión y comparar el hash calculado con `Metadata.sha256`:

```bash
export PF_KEY='raw/bestinver/AAAAMMDD/slug_kid.pdf'
export PF_VERSION='VERSION_ID_DE_LA_SALIDA'
aws s3api head-object --bucket "$PF_BUCKET" --key "$PF_KEY" \
  --version-id "$PF_VERSION" --region "$PF_REGION"
aws s3api get-object --bucket "$PF_BUCKET" --key "$PF_KEY" \
  --version-id "$PF_VERSION" --region "$PF_REGION" ./kid-comprobacion.pdf
shasum -a 256 ./kid-comprobacion.pdf
```

Para revisar el manifiesto, seleccionar su clave de `list-objects-v2` y descargarlo con `aws s3api get-object --bucket "$PF_BUCKET" --key '<clave-del-manifiesto>' --region "$PF_REGION" ./manifiesto-comprobacion.json`. Comparar sus entradas y contadores con los objetos, sus versiones y los errores mostrados. Una segunda ejecución puede crear versiones adicionales; no demuestra que P2 deduplique.

## 4. Qué falta para reproducir el proyecto completo

1. Definir mediante Terraform el almacenamiento de documentos o acordar la incorporación de uno ya existente; esta guía AWS CLI crea recursos fuera del estado Terraform y **no debe aplicarse Terraform sobre ellos sin planificar su importación o transición**.
2. Implementar las imágenes y Lambdas de captura, Step Functions y Scheduler; comprobar qué infraestructura existe antes de crear recursos compartidos.
3. Implementar P2: SQS/DLQ, consumidor, lectura de la versión exacta, procesamiento y base de datos con unicidad transaccional. Definir las notificaciones del bucket una sola vez y conservar las existentes.
4. Adaptar bootstrap OIDC, estados y workflows a la cuenta y repositorio de destino. Las variables de cuenta y ARN de los workflows actuales pertenecen al entorno del proyecto original; la creación del bucket de prueba no los cambia.
5. Acordar retención de versiones y manifiestos, permisos mínimos y cómo recuperar una ejecución interrumpida. Antes de eliminar un bucket versionado hay que considerar **todas las versiones y delete markers**, no solo los objetos actuales; esta guía no borra datos automáticamente.

Referencias oficiales: [crear un bucket con AWS CLI](https://docs.aws.amazon.com/AmazonS3/latest/userguide/GettingStartedS3CLI.html), [versionado de S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/manage-versioning-examples.html), [filtros de notificaciones](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-how-to-filtering.html) y [configuración de notificaciones](https://docs.aws.amazon.com/AmazonS3/latest/API/API_PutBucketNotificationConfiguration.html).
