# Respuesta de P2 a la propuesta C1 v1

**Estado:** P2 acepta [C1_PROPUESTA.md](C1_PROPUESTA.md) y la implementa en `procesamiento/`. Probado con tests y dobles de S3; **no** probado todavía con el bucket ni las colas reales (queda para el primer despliegue en dev).

## Qué acepta P2 y dónde está implementado

| Punto de C1 v1 | Implementación en P2 |
| --- | --- |
| Clave `raw/{gestora}/{AAAAMMDD}/{slug}_{tipo}.pdf`, tipos `kid` y `ficha_fondo` | `procesamiento/rutas.py`. El sufijo histórico `_datos_fundamentales` se sigue reconociendo, pero no dispara procesamiento. |
| Solo KID a P2, filtro `raw/` + `_kid.pdf` | Notificación S3 en `infra/modules/processing/main.tf` (`aws_s3_bucket_notification`). |
| Notificación nativa S3 `ObjectCreated` → SQS estándar | Una cola por etapa con DLQ tras 3 intentos. La política de cada cola solo admite `s3.amazonaws.com` desde ese bucket y esa cuenta. |
| Procesar todos los `Records`, decodificar con `unquote_plus` y usar el `versionId` del evento | `procesamiento/eventos.py`. Test con la fixture `events/pdf_created.json` tal cual. |
| Metadatos obligatorios: `gestora`, `tipo-documento`, `url-origen`, `fecha-descarga-utc`, `sha256`, `correlation-id` | `procesamiento/markdown.py` (`comprobar_c1`). Si falta alguno, o la gestora del metadato no coincide con la de la clave, queda `REJECTED` (`contrato_c1`) con JSON de auditoría y sin reintento. |
| Verificar el SHA-256 de la versión descargada | Si no coincide, `REJECTED` (`sha256_no_coincide`) y sin reintento. |
| Deduplicación lógica en P2, con restricción atómica | `documento.sha256` es único y `kid_version` es única por `(isin, fecha_documento, documento_id)`. Todo se escribe con `ON CONFLICT` en una transacción, así que dos consumidores concurrentes no duplican. |
| Conservar cada observación aunque el contenido ya exista | Tabla `documento_observacion`, única por `(bucket, key, versionId)` (`database/migrations/0003_observaciones.sql`). Un PDF repetido se registra como observación sin volver a llamar a Bedrock. |

## Casos de la tabla de idempotencia de C1, cubiertos por tests

| Caso | Resultado en P2 | Test |
| --- | --- | --- |
| Misma ejecución reintentada (mismos bytes, otra versión) | Un documento y dos observaciones | `test_mismo_contenido_reintentado_por_p1_es_otra_observacion` |
| Mismos bytes otro día | Sin otra versión de KID; nueva observación; JSON `VALID` con `duplicado: true` | `test_mismo_pdf_descargado_otro_dia_no_crea_otra_version` |
| Cambian los bytes el mismo día | Se reprocesa; dos documentos | `test_cambio_de_bytes_el_mismo_dia_es_otro_documento` |
| Evento duplicado | Sin otra llamada a Bedrock ni filas nuevas | `test_reentrega_del_mensaje_no_duplica_ni_llama_a_bedrock` |
| Versión posterior a la del evento | Se lee la versión del evento | `test_lee_la_version_exacta_del_evento` |
| Varios `Records` en un mensaje | Se procesan todos | `test_varios_records_en_un_mensaje` |

## Límites conocidos

- Las claves de C2 y C3 se derivan de la clave raw, no de su versión. Si la misma clave cambia de bytes el mismo día y los eventos llegan desordenados, la versión actual del `.md` y del `.json` puede ser la antigua. Aurora sigue siendo correcta, porque guarda los dos documentos por sha256 y la API elige el KID por `fecha_documento`. Además, el versionado del bucket conserva todas las versiones de `processed/`.
- La concurrencia real entre dos Lambdas solo está cubierta por las restricciones de la base de datos; no hay prueba de carga.
- El manifiesto de P1 no se usa: P2 no depende de él.

## Pendiente con P1/P3

1. Confirmar que nadie más declara `aws_s3_bucket_notification` para el bucket. La configuración la gestiona el estado `pipeline-fondos/dev/processing` y **reemplaza la que haya**; el workflow deja en el resumen la que había antes de aplicar.
2. Bootstrap: `infra/bootstrap/processing_cd_permissions.tf` reutiliza `capture_documents_bucket`. Lo aplica P3.
3. Primer despliegue: activar el Scheduler de captura solo después de que existan las colas y la notificación de P2, para no perder los primeros eventos.
