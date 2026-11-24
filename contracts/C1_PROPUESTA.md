# Propuesta C1 v1: captura y entrega de documentos

**Estado:** decisión de implementación de P1 para avanzar, pendiente de aceptación por P2/P3 y de prueba de integración. P1 ya publica las versiones y metadatos descritos; la deduplicación lógica y el consumidor todavía no existen. Las tareas 0.2 y 0.3 siguen abiertas hasta verificar la frontera completa.

## Objetivo y alternativas

Entregar a P2 KID identificables y recuperables, conservando la procedencia y evitando registros lógicos duplicados incluso si se repiten subidas o eventos.

| Alternativa | Mecanismo | Valoración inicial |
| --- | --- | --- |
| Actual | Subir con ruta por fecha, sin hash ni control de eventos. | Insuficiente para C1 e idempotencia. |
| Evento nativo + idempotencia en P2 | S3 versionado → evento → SQS; P2 consulta metadatos y deduplica en almacenamiento persistente. | Propuesta inicial: reutiliza el flujo previsto y evita coordinar un publicador de mensajes adicional. |
| Índice adicional en P1 | Registrar cada hash mediante un almacén con escritura condicional antes o después de subir. | Puede reducir subidas, pero añade coordinación y fallos entre dos escrituras; reconsiderar si las mediciones muestran que el coste de reprocesar lo justifica. |
| Manifiesto por lotes | P2 lee periódicamente los manifiestos, sin eventos por documento. | Simplifica notificaciones, pero cambia el procesamiento por eventos previsto y requiere programar y recuperar lotes. |
| Evento propio por documento | P1 publica un mensaje con todos los metadatos después de subir. | Evita una lectura de metadatos en P2, pero exige resolver de forma fiable el fallo entre subir y publicar. |

No se ha hecho una comparación experimental de coste ni fiabilidad. Esta es una recomendación provisional basada en el alcance actual; se probará con los escenarios de aceptación de abajo.

## Objeto y metadatos

- **Bucket:** configurable por entorno; `curso-miax-pipeline-fondos` es el destino histórico, no se presupone que sea gestionado por Terraform ni que cumpla las garantías. Antes de usarlo, comprobar propiedad, permisos, región, cifrado, bloqueo público y versionado. P1 y P2 deben tener acceso de mínimo privilegio.
- **Clave:** `raw/{gestora}/{AAAAMMDD}/{slug}_{tipo}.pdf`. La fecha es la fecha de descarga en `Europe/Madrid`; el instante exacto se registra en UTC. `slug` debe ser estable, seguro para una clave S3 y distinguir fondo y clase cuando sea necesario. Se documentarán y probarán colisiones por fuente.
- **Tipos:** `kid` y `ficha_fondo`; sufijos exactos `_kid.pdf` y `_ficha_fondo.pdf`. Conservar las fichas, pero enviar a P2 solo KID mediante filtro de evento `raw/` + `_kid.pdf`. Este nombre sustituye el sufijo histórico `_datos_fundamentales.pdf` para archivos nuevos.
- **Propiedad HTTP S3:** `Content-Type: application/pdf`. Antes de subir, rechazar respuestas vacías o que no pasen la validación PDF acordada; no confiar solo en la extensión o en la cabecera HTTP de origen.
- **Metadatos de usuario S3 obligatorios:** `gestora`, `tipo-documento` (`kid` o `ficha_fondo`), `url-origen`, `fecha-descarga-utc`, `sha256`, `correlation-id`. La fecha se expresa en ISO 8601 UTC, por ejemplo `2026-11-22T09:30:00Z`; el SHA-256 son 64 caracteres hexadecimales minúsculos calculados sobre los bytes descargados. La URL se almacena en representación ASCII con percent-encoding cuando sea necesario. El `correlation-id` identifica la ejecución y se propaga sin contener información sensible.
- **Versionado:** obligatorio antes de activar la ingesta. P2 usa el `versionId` del evento en `HeadObject` y `GetObject`; nunca presupone que la versión actual corresponde al evento. La retención de versiones debe cubrir colas, DLQ y reprocesado; el plazo concreto queda por configurar según la operación acordada.

Ejemplo de objeto y metadatos:

```text
s3://<bucket>/raw/bestinver/20261122/bestinfond-clase-c_kid.pdf
Content-Type: application/pdf
x-amz-meta-gestora: bestinver
x-amz-meta-tipo-documento: kid
x-amz-meta-url-origen: https://www.example.com/bestinfond.pdf
x-amz-meta-fecha-descarga-utc: 2026-11-22T09:30:00Z
x-amz-meta-sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
x-amz-meta-correlation-id: ejecucion-20261122-001
```

La URL y el hash son ilustrativos. El nombre del bucket se inyecta por configuración; no se versionan credenciales.

## Evento y lectura por P2

La propuesta es usar **notificaciones nativas S3 `ObjectCreated` → SQS estándar → consumidor de P2**. [`events/pdf_created.json`](events/pdf_created.json) es una fixture ilustrativa del evento nativo, no un mensaje propio con metadatos inventados. El ejemplo contiene valores ficticios y una clave codificada; el consumidor debe decodificarla como formulario URL, por ejemplo con `unquote_plus`. La configuración del bucket y su propiedad Terraform se coordinan con P2/P3. S3 puede entregar eventos repetidos o fuera de orden; el consumidor procesa todos los `Records`, decodifica la clave y usa `(bucket, key, versionId)` para localizar la versión exacta.

P2 consulta los metadatos de esa versión, valida tipo y campos obligatorios, descarga esa misma versión y verifica el SHA-256 antes de procesar. Un fallo técnico se reintenta según la política de la cola; un documento semánticamente rechazado debe registrarse sin reintentos infinitos. Los detalles de retención, visibilidad y DLQ se fijan al integrar P2.

## Idempotencia y concurrencia

Hay tres identidades distintas:

1. **Objeto físico:** `(bucket, key, versionId)`, para leer exactamente lo que causó el evento.
2. **Contenido:** `sha256` de los bytes, para reconocer el mismo PDF aunque llegue por otra fecha o clave.
3. **Resultado de negocio:** P2 define y garantiza en su base de datos la unicidad acordada de documento y versión lógica por ISIN/fecha/documento. Una restricción atómica y una operación transaccional son necesarias para que dos consumidores concurrentes no creen dos registros; una consulta previa por sí sola no basta.

La decisión para P1 es **conservar las subidas y delegar la deduplicación lógica a P2**, sin añadir un índice global en P1. Así P1 no promete evitar eventos ni versiones físicas duplicadas. P2 debe guardar la asociación de cada observación con la fuente aunque su contenido ya exista; un hash igual no demuestra por sí solo que dos referencias de gestora o clase sean la misma relación de negocio.

| Caso | P1 | P2: resultado esperado |
| --- | --- | --- |
| Misma ejecución reintentada, mismos bytes y clave | Puede crear otra versión y otro evento; registrar ambos intentos. | Un único documento por hash y asociaciones de procedencia preservadas. |
| Mismos bytes en otro día | Nueva clave y evento; el manifiesto registra la observación. | No crear otro documento lógico por el mismo contenido; conservar la nueva observación. |
| Cambian los bytes el mismo día | Misma clave, nueva versión S3 y hash. | Leer ambas versiones exactas y tratar el nuevo hash como contenido distinto; aplicar las reglas de versión de negocio. |
| Dos capturas simultáneas | Pueden crear versiones y eventos separados. | La operación atómica de P2 impide registros duplicados; guardar o reconciliar ambas procedencias. |
| Evento duplicado o fuera de orden | No se presupone orden ni entrega única. | Repetir de forma segura; usar la versión del evento, no la última versión de la clave. |
| Subida correcta y fallo antes de escribir manifiesto | El evento y el objeto pueden existir sin reflejo final en el manifiesto. | Procesar el objeto; P1 debe indicar ejecución incompleta y permitir reconciliación. |

No se garantiza que el hash sea único por clase o gestora: un mismo PDF puede describir varias clases. La relación de procedencia y la unicidad exacta de la versión de negocio deben revisarse con P2 antes de fijar su esquema. No se afirman garantías de una sola ejecución ni de entrega exactamente una vez.

## Manifiesto de P1

Propuesta: un JSON final por intento y gestora bajo `manifests/{gestora}/{AAAAMMDD}/{execution_id}/{attempt_id}.json`, fuera del prefijo que dispara el procesamiento PDF. Definir y conservar ambos identificadores en la orquestación. El manifiesto contiene versión de esquema, ejecución, intento, gestora, inicio y fin UTC, estado (`completa`, `parcial` o `fallida`), contadores y una entrada por documento detectado o fallo conocido: origen, tipo, identidad de producto/clase cuando esté disponible, resultado, error cuando corresponda, hash y `(bucket, key, versionId)` cuando la subida haya sido confirmada.

Implementación local de Bestinver: el segmento de ejecución en la clave es el SHA-256 del `correlation_id` para evitar caracteres inseguros; el ID original se conserva en el JSON. El identificador de intento es un UUID nuevo. La vinculación con identificadores de la futura orquestación queda por integrar.

Un documento ausente, un fallo de listado y un fallo de descarga o subida deben poder distinguirse; no se inventan claves ni hashes no conocidos. Se conserva el manifiesto al menos durante el periodo operativo y de auditoría que acuerde el equipo. El manifiesto es **auditoría, no garantía transaccional**: una interrupción puede ocurrir antes de escribirlo, y un timeout de subida puede dejar su resultado incierto. Los logs y la reconciliación con S3 deben hacer visibles esas situaciones; P2 no depende de la presencia del manifiesto para recibir un evento.

## Ejemplos de resultados del manifiesto

Estos fragmentos ilustran campos relevantes; las claves, identificadores y hashes son ficticios. El JSON completo añade los campos temporales, contadores y datos del documento descritos arriba.

| Situación | Campos relevantes |
| --- | --- |
| Subida confirmada | `estado: completa`; `subidos` contiene `clave`, `version_id` y `sha256`. |
| Una subida correcta y otra fallida | `estado: parcial`; `subidos` conserva la versión confirmada y `fallos` identifica la etapa y el origen del documento fallido. |
| Resultado incierto de subida | `fallos` contiene `etapa: subida_resultado_incierto`, `clave` y el `sha256` calculado; no se inventa un `versionId`. Reconciliar esa clave y hash con las versiones de S3 antes de decidir un reintento. |
| Fallo al guardar el manifiesto | La ejecución informa `manifiesto_resultado_incierto`; el propio manifiesto puede no existir o haberse guardado pese al error. Consultar logs, ejecuciones y versiones en S3. |

La prueba de S3 real cubre las versiones físicas; los ejemplos de arriba no prueban una deduplicación lógica de P2.

## Verificación antes de dar 0.2 y 0.3 por terminadas

- [ ] Revisar y aceptar con P2 tipos, ruta, metadatos, evento, política de fichas, identidades y asociación de procedencias.
- [ ] Acordar con P3/P2 bucket y propiedad de la configuración de eventos; comprobar versionado, permisos y retención.
- [x] Versionar un ejemplo ilustrativo del evento nativo seleccionado.
- [x] Documentar ejemplos de manifiesto con éxito, fallo parcial y resultado incierto.
- [ ] Probar el consumidor de P2 con claves codificadas, eventos repetidos y fuera de orden; validar los casos de concurrencia y cambio el mismo día con su almacenamiento real. P1 ya comprobó versiones exactas, cambios y concurrencia en S3 real, pero eso no valida el consumidor.
- [ ] Documentar el resultado, límites y política de reconciliación. Una propuesta escrita no equivale a aceptación de P2 ni a una prueba de integración.

Referencias AWS: [estructura de eventos S3](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html), [filtros por prefijo y sufijo](https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-how-to-filtering.html), [lectura de metadatos de una versión](https://docs.aws.amazon.com/AmazonS3/latest/userguide/RetMetaOfObjVersion.html) y [escrituras condicionales](https://docs.aws.amazon.com/AmazonS3/latest/userguide/conditional-writes.html).
