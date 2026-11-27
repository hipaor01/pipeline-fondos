# Automatización de la captura P1 en una cuenta de pruebas

**Estado:** desplegado y probado en noviembre de 2026 en una cuenta personal de pruebas (`eu-west-3`). No representa un despliegue en la cuenta compartida ni la integración de P2. El horario diario permanece desactivado.

## Qué despliega

```text
ECR (imagen ARM64 compartida) → Lambda Bestinver ┐
                            → Lambda Azvalor    ├→ resultados → comprobación de estado
Scheduler → Step Functions  → Lambda Cobas      ┘
```

Cada Lambda utiliza el mismo código de ingesta que la CLI y un rol propio con acceso de escritura limitado a los prefijos de su gestora en el bucket configurado. Las tres ramas se invocan en paralelo. Cada rama captura sus propios errores para que las otras puedan terminar; después, si cualquiera ha fallado o terminado parcialmente, la ejecución de Step Functions termina en `CapturaIncompleta`. Los detalles de las ramas están en el historial y los manifiestos de S3.

El Scheduler diario se crea **desactivado**, configurado a las 07:00 de `Europe/Madrid`. La captura produce nuevas versiones físicas incluso con contenido idéntico: la deduplicación lógica, el consumidor P2 y la decisión sobre su programación definitiva siguen pendientes. `robots.txt` de Azvalor devolvió HTTP 418 en el análisis previo; sus reglas siguen sin verificar. No se configuran notificaciones S3 ni recursos de P2 con esta guía.

Se propuso una imagen común porque las tres fuentes se han capturado mediante HTML y las dependencias son las mismas. Las alternativas consideradas fueron mantener la CLI manual, empaquetar un ZIP Lambda o usar una imagen por gestora. La CLI no cubre la programación, y las imágenes independientes y el ZIP no se han medido en una comparación equivalente; no se afirma que la imagen común sea más rápida o barata. La imagen común se ha construido localmente para Linux ARM64 y se ha probado su arranque con el emulador Lambda. Las dependencias vienen de `uv.lock`; las etiquetas de imágenes base pueden cambiar con el tiempo.

## Antes de empezar

- Python 3.14, `uv`, Docker con Buildx, AWS CLI v2, Terraform >= 1.10, `jq` y permisos para ECR, Lambda, IAM, CloudWatch Logs, CloudWatch, SQS, Step Functions y Scheduler en la cuenta de prueba.
- Un bucket de documentos existente, privado y versionado en `eu-west-3`, como el preparado siguiendo [GUIA_AWS_CAPTURA.md](GUIA_AWS_CAPTURA.md). Confirmar la cuenta y el bucket antes de seguir; los comandos crean recursos y las ejecuciones generan versiones nuevas y costes.
- Tres raíces Terraform independientes: [`storage`](../infra/environments/dev/storage/README.md) crea un bucket o referencia uno existente sin gestionarlo; `capture-registry` crea ECR; `capture` recibe el digest de la imagen y crea las Lambdas y la orquestación. Las tres tienen claves independientes en el backend S3; `storage` continúa separado y no se aplica desde el workflow. Si existen recursos administrados por un estado local anterior, migrar ese estado de forma explícita antes de inicializar el backend remoto para evitar intentar recrearlos.

## 1. Cuenta, bucket y validación local

```bash
aws sts get-caller-identity
export PF_REGION=eu-west-3
export PF_BUCKET='NOMBRE-DE-TU-BUCKET-DE-PRUEBA'
aws s3api get-bucket-versioning --bucket "$PF_BUCKET" --region "$PF_REGION"
uv run --locked --group dev --group frontend --group scraping pytest -q
export PF_STATE_BUCKET='pipeline-fondos-terraform-state-065451207233'
terraform -chdir=infra/environments/dev/capture-registry init \
  -backend-config="bucket=$PF_STATE_BUCKET"
terraform -chdir=infra/environments/dev/capture init \
  -backend-config="bucket=$PF_STATE_BUCKET"
terraform -chdir=infra/environments/dev/capture-registry validate
terraform -chdir=infra/environments/dev/capture validate
terraform -chdir=infra/environments/dev/capture test
```

El bucket debe mostrar `Enabled`. Tras activarlo por primera vez, esperar los 15 minutos de propagación recomendados por AWS antes de escribir. La validación Terraform y los tests simulados no sustituyen la prueba real en la cuenta. Para crear o referenciar almacenamiento con Terraform, seguir la [guía de storage](../infra/environments/dev/storage/README.md).

## 2. Crear ECR y publicar la imagen

Revisar el plan antes de aplicarlo. El módulo del repositorio impide su destrucción accidental. Solo considera para expiración las imágenes con etiqueta `desechable-` y conserva las 30 más recientes de ellas. Las demás permanecen y generan costes de almacenamiento. **No etiquetar como desechable un digest activo o necesario para rollback**, aunque tenga otras etiquetas: ECR puede eliminar la imagen completa. El nombre del repositorio es independiente del bucket de documentos.

```bash
terraform -chdir=infra/environments/dev/capture-registry plan -out=registro.tfplan
terraform -chdir=infra/environments/dev/capture-registry apply registro.tfplan
export PF_REPO="$(terraform -chdir=infra/environments/dev/capture-registry output -raw repository_url)"
export PF_REPO_NAME="${PF_REPO#*/}"
export PF_REGISTRY="${PF_REPO%%/*}"
export PF_TAG="prueba-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
docker buildx build --platform linux/arm64 --provenance=false --load \
  -f Dockerfile.scraper -t "${PF_REPO}:${PF_TAG}" .
aws ecr get-login-password --region "$PF_REGION" | \
  docker login --username AWS --password-stdin "$PF_REGISTRY"
docker push "${PF_REPO}:${PF_TAG}"
export PF_DIGEST="$(aws ecr describe-images --region "$PF_REGION" \
  --repository-name "$PF_REPO_NAME" --image-ids "imageTag=$PF_TAG" \
  --query 'imageDetails[0].imageDigest' --output text)"
export PF_IMAGE="${PF_REPO}@${PF_DIGEST}"
printf 'Imagen a desplegar: %s\n' "$PF_IMAGE"
```

El digest fija la imagen desplegada. Un tag aleatorio identifica el build sin suponer que el árbol local coincida con un commit de Git.

## 3. Desplegar las tres funciones y la orquestación

```bash
terraform -chdir=infra/environments/dev/capture plan \
  -var="documents_bucket=$PF_BUCKET" -var="image_uri=$PF_IMAGE" \
  -out=captura.tfplan
terraform -chdir=infra/environments/dev/capture apply captura.tfplan
export PF_STATE_MACHINE="$(terraform -chdir=infra/environments/dev/capture output -raw state_machine_arn)"
terraform -chdir=infra/environments/dev/capture output
aws scheduler get-schedule --region "$PF_REGION" --name pipeline-fondos-dev-capture-daily
```

El schedule debe estar `DISABLED` y su zona ser `Europe/Madrid`. La cola `scheduler_failures_queue_url` guarda los errores al iniciar Step Functions; su alarma CloudWatch es visible en consola, pero no envía notificaciones por sí sola. Los fallos posteriores de una ejecución se consultan en Step Functions. El Scheduler no reintenta automáticamente el inicio para evitar posibles ejecuciones duplicadas. Una ejecución completa puede tardar varios minutos por las pausas HTTP; cada Lambda tiene 900 segundos de timeout y 512 MiB.

## 4. Ejecutar y verificar manualmente

Este comando ejecuta las tres ramas y escribe documentos reales y manifiestos en el bucket. Un nuevo intento crea versiones adicionales en S3:

```bash
export PF_EXEC_NAME="manual-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
export PF_EXEC_ARN="$(aws stepfunctions start-execution --region "$PF_REGION" \
  --state-machine-arn "$PF_STATE_MACHINE" --name "$PF_EXEC_NAME" \
  --input '{}' --query executionArn --output text)"
aws stepfunctions describe-execution --region "$PF_REGION" --execution-arn "$PF_EXEC_ARN"
aws stepfunctions get-execution-history --region "$PF_REGION" --execution-arn "$PF_EXEC_ARN"
```

Consultar `describe-execution` hasta que deje de estar `RUNNING`. Una ejecución `SUCCEEDED` requiere `completa` en las tres ramas. Si es `FAILED`, consultar el historial y los logs `/aws/lambda/pipeline-fondos-dev-capture-<gestora>`; una rama parcial o fallida no debe interpretarse como éxito aunque las otras hayan terminado. Revisar `raw/` y `manifests/` para cada gestora y comprobar versiones, metadatos y hashes como en la guía S3.

Las ramas solo reintentan automáticamente `Lambda.TooManyRequestsException`, cuando la invocación ha sido rechazada por límite de servicio. Los fallos de ejecución y tiempos de espera no se reintentan automáticamente: una ejecución que ya haya subido parte de los documentos podría generar más versiones al reintentarse.

Para validar la definición desplegada y simular un error en una rama sin modificar las funciones:

```bash
aws stepfunctions describe-state-machine --region "$PF_REGION" \
  --state-machine-arn "$PF_STATE_MACHINE" --query definition --output text > /tmp/pf-state-machine.json
aws stepfunctions validate-state-machine-definition --region "$PF_REGION" \
  --definition file:///tmp/pf-state-machine.json --type STANDARD --severity WARNING
jq -c '.States.Capturar.Branches[0].States["Invocar-bestinver"]' \
  /tmp/pf-state-machine.json > /tmp/pf-branch.json
aws stepfunctions test-state --region "$PF_REGION" \
  --definition file:///tmp/pf-branch.json --input '{}' \
  --mock '{"errorOutput":{"error":"Lambda.ServiceException","cause":"error simulado"}}'
```

El resultado esperado del último comando es `CAUGHT_ERROR` con `nextState` igual a `Fallo-bestinver`. Esta simulación comprueba el `Catch` de una rama; por sí sola no demuestra que las otras dos terminen. La prueba real descrita al final de esta guía completó además esa comprobación de ejecución paralela con un fallo controlado.

## 5. Probar Scheduler sin activar el horario diario

La siguiente prueba crea un schedule **de una sola ejecución** con borrado automático, que iniciará la máquina de estados unos dos minutos después. Dispara las tres capturas y crea más versiones S3. Ejecutarla cuando no haya otras ejecuciones concurrentes para poder identificar el resultado:

```bash
export PF_SCHEDULER_ROLE="$(terraform -chdir=infra/environments/dev/capture output -raw scheduler_role_arn)"
export PF_ONCE="prueba-p1-$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
export PF_AT="$(python3 -c 'from datetime import datetime,timedelta,timezone; print((datetime.now(timezone.utc)+timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S"))')"
export PF_TARGET="$(jq -cn --arg arn "$PF_STATE_MACHINE" --arg role "$PF_SCHEDULER_ROLE" \
  '{Arn:$arn,RoleArn:$role,Input:"{}",RetryPolicy:{MaximumRetryAttempts:0,MaximumEventAgeInSeconds:60}}')"
aws stepfunctions list-executions --region "$PF_REGION" --state-machine-arn "$PF_STATE_MACHINE" --max-results 10
aws scheduler create-schedule --region "$PF_REGION" --name "$PF_ONCE" \
  --schedule-expression "at($PF_AT)" --schedule-expression-timezone UTC \
  --flexible-time-window Mode=OFF --action-after-completion DELETE --target "$PF_TARGET"
printf 'Schedule %s previsto para %s UTC\n' "$PF_ONCE" "$PF_AT"
```

Después de la hora indicada, consultar de nuevo `list-executions`, identificar la ejecución nueva y verificarla con `describe-execution` e historial. Comprobar con `get-schedule` que el schedule de una sola ejecución se ha eliminado y que `pipeline-fondos-dev-capture-daily` continúa desactivado. El borrado automático puede tardar; si la ejecución no aparece, revisar CloudWatch y los permisos del rol Scheduler. No confundir creación del schedule con prueba de que la captura haya terminado correctamente.

### Consultar fallos al iniciar la captura

La DLQ pertenece a Scheduler de P1 y no es la cola de procesamiento de P2. Si Scheduler no puede iniciar la máquina de estados, deposita el evento fallido aquí; los fallos de una ejecución ya iniciada se consultan en el historial de Step Functions. La alarma cambia de estado si hay mensajes visibles, pero no envía notificaciones mientras no se configure un destinatario.

```bash
export PF_SCHEDULER_DLQ="$(terraform -chdir=infra/environments/dev/capture output -raw scheduler_failures_queue_url)"
aws sqs get-queue-attributes --region "$PF_REGION" --queue-url "$PF_SCHEDULER_DLQ" \
  --attribute-names ApproximateNumberOfMessages
aws cloudwatch describe-alarms --region "$PF_REGION" \
  --alarm-names pipeline-fondos-dev-capture-scheduler-failures
```

El 25-11-2026, en la cuenta personal, un schedule temporal apuntó a una máquina inexistente y produjo `AccessDeniedException`; el mensaje llegó a la DLQ y la alarma cambió a `ALARM`. Se retiró solo el mensaje de prueba. La programación diaria permaneció desactivada.

## 6. Activar o detener la programación diaria

Solo cuando las reglas de las fuentes y la integración de datos estén resueltas, aplicar el mismo digest y bucket con `-var='schedule_enabled=true'`. Para detenerla, aplicar con `-var='schedule_enabled=false'`. Mantener presentes todas las variables en ambos comandos para evitar un plan inesperado y revisarlo antes de aplicar. No se incluye una eliminación automática del bucket ni de sus versiones; los estados y el repositorio ECR deben conservarse o retirarse mediante un procedimiento explícito.

## Resultados de la prueba en AWS (24-11-2026)

En una cuenta personal, con un bucket privado y versionado ya existente, se creó ECR, se publicó una imagen ARM64 por digest y se desplegaron tres Lambdas, Step Functions y Scheduler. La ejecución manual `manual-p1-0a1ed5e8c488` terminó `SUCCEEDED`: Bestinver subió 37 documentos, Azvalor 21 y Cobas 44. Sus manifiestos registraron respectivamente 11, 1 y 0 documentos ausentes. Se descargaron las 102 versiones exactas y se verificaron PDF, SHA-256, `Content-Type`, metadatos y referencias de manifiesto. El contenido disponible en las fuentes puede variar entre ejecuciones.

Un schedule temporal de una sola ejecución inició correctamente la máquina a las 20:51 (hora de Madrid) y terminó `SUCCEEDED` a las 20:52, con 37, 21 y 44 documentos respectivamente. El schedule temporal se eliminó automáticamente y el diario permaneció `DISABLED`.

Para comprobar el aislamiento, se creó una máquina temporal con la misma definición y una ARN de Lambda inexistente en la rama de Bestinver. Esa invocación falló por permisos, Azvalor y Cobas terminaron correctamente y la ejecución completa terminó `FAILED` con `CapturaIncompleta`. Se eliminó la máquina temporal. También se usó `test-state` para comprobar el `Catch`, el reintento por limitación de Lambda y la elección entre éxito y fallo. La primera aplicación detectó que Step Functions exige nombres de estado únicos entre ramas; se corrigieron los nombres, se validó la definición con la API de AWS y se aplicó el plan restante.

Se probó además, de forma aislada, un filtro nativo S3 → SQS con prefijo temporal `raw/p1-event-test/` y sufijo `_kid.pdf`: llegó un evento para el KID con el `VersionId` correcto y no se observó evento para la ficha durante 35 segundos. Se verificó la versión mediante `GetObject`, su contenido, hash y tipo. La prueba usó una cola temporal con política restringida al bucket y a la cuenta; después se eliminaron las versiones de prueba y la cola, y se restauró la configuración vacía anterior de notificaciones. S3 puede entregar eventos duplicados o tardíos; esta observación no demuestra entrega exactamente una vez. P2 deberá implementar y probar su consumidor, su idempotencia y la configuración definitiva de notificaciones junto con P3.

En la revisión posterior del mismo día se reconstruyó la imagen con la corrección para detectar una captura de Bestinver sin ningún KID. Un plan Terraform actualizó únicamente las tres Lambdas; una invocación real de Bestinver registró 37 subidos, 11 ausentes y ningún fallo, con las 37 versiones reconciliadas por hash y `correlation_id`. El caso sin KID se probó con respuestas controladas localmente.

Las ejecuciones reales crean versiones adicionales en S3 y consumen servicios de AWS. Las raíces `capture-registry` y `capture` usan estados remotos separados y el workflow despliega mediante OIDC; cualquier estado local que hubiera administrado los mismos recursos debe migrarse antes del primer despliegue. La ejecución real del nuevo workflow en GitHub sigue pendiente para estos cambios.

## Repetir la prueba aislada de eventos S3

Esta prueba usa una cola y dos versiones temporales en el bucket de pruebas. Requiere AWS CLI, `jq` y permisos S3/SQS. Ejecutarla **solo si el bucket no tiene notificaciones**, porque `put-bucket-notification-configuration` reemplaza toda la configuración. No es un consumidor P2. Para evitar interferir con las capturas, el prefijo es exclusivo de la prueba.

```bash
export PF_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
export PF_TEST_ID="$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')"
export PF_TEST_PREFIX="raw/p1-event-test/$PF_TEST_ID/"
export PF_QUEUE_NAME="p1-event-test-$PF_TEST_ID"
export PF_TMP="$(mktemp -d)"
aws s3api get-bucket-notification-configuration --bucket "$PF_BUCKET" --region "$PF_REGION" --output json > "$PF_TMP/antes.json"
# AWS CLI puede imprimir una respuesta vacía para una configuración vacía.
[ -s "$PF_TMP/antes.json" ] || printf "{}\n" > "$PF_TMP/antes.json"
# Abortamos si existe cualquier configuración; no reemplazar recursos ajenos.
jq -e 'length == 0' "$PF_TMP/antes.json" >/dev/null || { echo 'Bucket con notificaciones: detener la prueba'; return 1 2>/dev/null || exit 1; }
export PF_QUEUE_URL="$(aws sqs create-queue --region "$PF_REGION" --queue-name "$PF_QUEUE_NAME" --query QueueUrl --output text)"
export PF_QUEUE_ARN="$(aws sqs get-queue-attributes --region "$PF_REGION" --queue-url "$PF_QUEUE_URL" --attribute-names QueueArn --query Attributes.QueueArn --output text)"
jq -cn --arg arn "$PF_QUEUE_ARN" --arg bucket "$PF_BUCKET" --arg account "$PF_ACCOUNT" \
  '{Version:"2012-10-17",Statement:[{Effect:"Allow",Principal:{Service:"s3.amazonaws.com"},Action:"sqs:SendMessage",Resource:$arn,Condition:{ArnEquals:{"aws:SourceArn":("arn:aws:s3:::"+$bucket)},StringEquals:{"aws:SourceAccount":$account}}}]}' > "$PF_TMP/policy.json"
jq -cn --rawfile policy "$PF_TMP/policy.json" '{Policy:$policy}' > "$PF_TMP/attributes.json"
aws sqs set-queue-attributes --region "$PF_REGION" --queue-url "$PF_QUEUE_URL" --attributes "file://$PF_TMP/attributes.json"
jq -cn --arg arn "$PF_QUEUE_ARN" --arg id "$PF_TEST_ID" --arg prefix "$PF_TEST_PREFIX" \
  '{QueueConfigurations:[{Id:("p1-test-"+$id),QueueArn:$arn,Events:["s3:ObjectCreated:*"],Filter:{Key:{FilterRules:[{Name:"prefix",Value:$prefix},{Name:"suffix",Value:"_kid.pdf"}]}}}]}' > "$PF_TMP/notificaciones.json"
# Si aparece un error de validación de destino, esperar la propagación de la política y repetir.
aws s3api put-bucket-notification-configuration --region "$PF_REGION" --bucket "$PF_BUCKET" --notification-configuration "file://$PF_TMP/notificaciones.json"
printf '%%PDF-1.4\n%% isolated event test\n%%%%EOF\n' > "$PF_TMP/prueba.pdf"
export PF_KID_VERSION="$(aws s3api put-object --region "$PF_REGION" --bucket "$PF_BUCKET" --key "${PF_TEST_PREFIX}ejemplo_kid.pdf" --body "$PF_TMP/prueba.pdf" --content-type application/pdf --query VersionId --output text)"
export PF_FICHA_VERSION="$(aws s3api put-object --region "$PF_REGION" --bucket "$PF_BUCKET" --key "${PF_TEST_PREFIX}ejemplo_ficha.pdf" --body "$PF_TMP/prueba.pdf" --content-type application/pdf --query VersionId --output text)"
aws sqs receive-message --region "$PF_REGION" --queue-url "$PF_QUEUE_URL" --wait-time-seconds 20 --max-number-of-messages 10 > "$PF_TMP/mensajes.json"
jq -r '.Messages[]?.Body | fromjson | .Records[]? | [.s3.object.key,.s3.object.versionId] | @tsv' "$PF_TMP/mensajes.json"
aws s3api get-object --region "$PF_REGION" --bucket "$PF_BUCKET" --key "${PF_TEST_PREFIX}ejemplo_kid.pdf" --version-id "$PF_KID_VERSION" "$PF_TMP/recuperado.pdf"
cmp "$PF_TMP/prueba.pdf" "$PF_TMP/recuperado.pdf"
```

Puede llegar primero el mensaje de prueba de S3; repetir `receive-message` hasta encontrar el KID. Comparar su clave y versión con las variables y observar durante un intervalo adicional que no aparece la ficha. Los eventos son asíncronos y pueden repetirse. Para limpiar, primero verificar que la configuración actual contiene **solo** la cola y el identificador creados. Si otra persona la ha cambiado, no reemplazarla ni borrar la cola: coordinar la limpieza.

```bash
aws s3api get-bucket-notification-configuration --region "$PF_REGION" --bucket "$PF_BUCKET" > "$PF_TMP/actual.json"
jq -e --arg arn "$PF_QUEUE_ARN" --arg id "p1-test-$PF_TEST_ID" --arg prefix "$PF_TEST_PREFIX" \
  'keys == ["QueueConfigurations"] and (.QueueConfigurations | length == 1) and
   .QueueConfigurations[0].QueueArn == $arn and .QueueConfigurations[0].Id == $id and
   .QueueConfigurations[0].Events == ["s3:ObjectCreated:*"] and
   ([.QueueConfigurations[0].Filter.Key.FilterRules[] | [(.Name | ascii_downcase), .Value]] | sort) == ([["prefix",$prefix],["suffix","_kid.pdf"]] | sort)' \
  "$PF_TMP/actual.json" >/dev/null || { echo 'Configuración modificada: coordinar limpieza'; return 1 2>/dev/null || exit 1; }
aws s3api put-bucket-notification-configuration --region "$PF_REGION" --bucket "$PF_BUCKET" --notification-configuration "file://$PF_TMP/antes.json"
aws s3api delete-object --region "$PF_REGION" --bucket "$PF_BUCKET" --key "${PF_TEST_PREFIX}ejemplo_kid.pdf" --version-id "$PF_KID_VERSION"
aws s3api delete-object --region "$PF_REGION" --bucket "$PF_BUCKET" --key "${PF_TEST_PREFIX}ejemplo_ficha.pdf" --version-id "$PF_FICHA_VERSION"
aws sqs delete-queue --region "$PF_REGION" --queue-url "$PF_QUEUE_URL"
```

Si se interrumpe la prueba, conservar los valores `PF_*` y revisar manualmente las notificaciones, versiones y cola temporales antes de retirarlos. No borrar el bucket ni versiones que no pertenezcan a la prueba.

## Verificar versiones y permisos en la cuenta de pruebas

La prueba optativa siguiente usa la implementación real `subir_s3`: sube contenido repetido, contenido cambiado en la misma clave, otro día y dos escrituras simultáneas. Lee las seis versiones por `VersionId` y comprueba bytes, tipo y SHA-256. Utiliza un prefijo aleatorio propio y elimina únicamente sus versiones, incluso si una comprobación falla. Requiere permisos para listar y eliminar versiones de ese prefijo; nunca usarla en un bucket compartido sin revisar sus notificaciones, porque genera eventos de objetos.

```bash
export AWS_REGION=eu-west-3
export P1_TEST_BUCKET="$PF_BUCKET"
uv run --locked --group dev --group scraping pytest -q tests/webscrapper/test_s3_real.py
unset P1_TEST_BUCKET
```

Resultado del 24-11-2026 en la cuenta personal: seis versiones diferentes, dos hashes para los dos contenidos y recuperación correcta de cada versión; se verificó que no quedaran objetos de prueba bajo `raw/p1-test-versiones/`. Una repetición física no equivale a un resultado de negocio duplicado ni valida la deduplicación futura de P2.

La inspección real del bucket confirmó bloqueo de acceso público en sus cuatro opciones, cifrado por defecto AES-256 y versionado activo; no había política de bucket ni notificaciones configuradas. Los tres grupos de logs tenían retención de 14 días. Mediante `aws iam simulate-principal-policy` se comprobó para cada rol de gestora que `s3:PutObject` estaba permitido en sus propios prefijos `raw/` y `manifests/`, y denegado implícitamente en el prefijo `raw/` de otra gestora. La simulación comprueba esas acciones y recursos concretos, no todas las combinaciones posibles ni la configuración de la cuenta compartida. Para repetirla, sustituir los valores por los propios:

```bash
export PF_ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
aws iam simulate-principal-policy --region "$PF_REGION" \
  --policy-source-arn "arn:aws:iam::$PF_ACCOUNT:role/pipeline-fondos-dev-capture-bestinver" \
  --action-names s3:PutObject \
  --resource-arns "arn:aws:s3:::$PF_BUCKET/raw/bestinver/prueba.pdf" \
                  "arn:aws:s3:::$PF_BUCKET/raw/cobas/prueba.pdf" \
                  "arn:aws:s3:::$PF_BUCKET/manifests/bestinver/prueba.json" \
  --query 'EvaluationResults[].ResourceSpecificResults[].[EvalResourceName,EvalResourceDecision]'
```

En la simulación se espera `allowed`, `implicitDeny` y `allowed`, respectivamente. Verificar también política del bucket, límites de permisos y SCP cuando existan: esta prueba no sustituye una revisión integral de acceso.
