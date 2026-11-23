# Procesamiento y datos (P2)

PDF del KID en S3 → Markdown → datos estructurados con Amazon Bedrock → Aurora PostgreSQL.

```
S3 raw/{gestora}/{AAAAMMDD}/{slug}_{tipo}.pdf                         (C1, lo escribe P1)
  │  EventBridge "Object Created" raw/*.pdf
  ▼
SQS pdf-markdown (DLQ tras 3 intentos) ─► Lambda pdf-markdown (batch=1, máx. 2 en paralelo)
  │                                         pymupdf4llm, sin OCR por defecto
  ▼
S3 processed/markdown/{gestora}/{AAAAMMDD}/{slug}_{tipo}.md            (C2)
  │  EventBridge "Object Created" processed/markdown/*.md
  ▼
SQS extraccion (DLQ tras 3 intentos) ─► Lambda extraccion (batch=1, máx. 2 en paralelo)
                                          ├─ Bedrock Converse + outputConfig.textFormat (JSON Schema)
                                          ├─ validación de evidencias y reglas
                                          ├─► S3 processed/structured/...json  SIEMPRE      (C3)
                                          └─► Aurora (Data API) solo si VALID              (C4)
```

## Estados (contrato C3)

| Estado | Cuándo | Qué pasa |
|---|---|---|
| `VALID` | Pasa todas las reglas | JSON de auditoría + upsert en Aurora |
| `REJECTED` | Problema semántico: falta un obligatorio, evidencia que no aparece en el documento, valor fuera de rango, ISIN con dígito de control incorrecto, no es un KID, PDF sin texto | JSON de auditoría con `motivo` y `datos_crudos`; **no se reintenta** |
| `ERROR` | Problema técnico: Bedrock, S3, Aurora | SQS reintenta; en el último intento se deja el JSON `ERROR` y el mensaje va a la DLQ |

Reglas de validación (`procesamiento/validacion.py`):

- Obligatorios: `isin`, `nombre_producto`, `gestora`, `sri`.
- **Todo valor no nulo exige evidencia y la evidencia tiene que aparecer en el Markdown** (comparación sin espacios ni marca Markdown, porque pymupdf4llm parte palabras entre celdas de tabla).
- El ISIN debe aparecer en su propia evidencia y tener dígito de control válido.
- Rangos: SRI 1–7, porcentajes 0–100, periodo ≥ 0.
- Solo avisa (no rechaza) si un número no aparece literalmente en su evidencia: «No cobramos comisión de entrada» → 0 % es correcto.

## Idempotencia

- **Markdown**: si ya existe el `.md` con el mismo `pdf-sha256`, no se reescribe (y no se dispara otra extracción).
- **Reentrega del mensaje**: si ya hay JSON `VALID`/`REJECTED` para ese sha256 y versión de esquema, no se vuelve a llamar a Bedrock; si era `VALID` se repite la carga (idempotente) por si falló Aurora.
- **Mismo PDF descargado otro día**: si el sha256 ya está en Aurora, se audita como `VALID` con `duplicado: true` sin llamar a Bedrock.
- **Aurora**: `documento.sha256` único y `kid_version` única por `(isin, fecha_documento, documento_id)` con `NULLS NOT DISTINCT`; todos los `INSERT` usan `ON CONFLICT` y van en una transacción.

## Base de datos (contrato C4)

Migraciones en `database/migrations/`: tablas `gestora`, `fondo`, `clase_fondo`, `documento`, `kid_version` y dos vistas de lectura para la API:

- `api_kid_version`: una fila por versión de KID, con las columnas de `api/models/kid.py`.
- `api_fondo`: el KID más reciente de cada ISIN, con las columnas de `api/models/fondo.py`.

Un test comprueba que lo que devuelven las vistas valida contra los modelos Pydantic de la API, así que si alguien cambia uno de los dos lados, el test falla.

```bash
# Local
python -m procesamiento.datos.migraciones --dsn postgresql://localhost/fondos
# Aurora (lo hace la pipeline después de terraform apply)
python -m procesamiento.datos.migraciones --cluster-arn ... --secret-arn ... --base-datos fondos
```

## Decisiones y por qué

| Decisión | Motivo |
|---|---|
| **Imagen de contenedor**, no ZIP | `pymupdf4llm` 2.1 instala `pymupdf` + `onnxruntime` + `numpy`: 252 MB sin comprimir medidos, por encima de los 250 MB de un ZIP de Lambda. Una sola imagen para las dos Lambdas (cambia el `command`). |
| **Sin OCR por defecto** | Los KID de Bestinver tienen texto: conversión en ~1 s. «OCR se mide antes de mantenerlo en Lambda»: un PDF sin texto queda `REJECTED` con motivo `markdown_vacio` y se ve en las métricas. |
| **EventBridge** en vez de notificación S3 | La notificación es un único recurso por bucket (de P1); con EventBridge cada etapa crea su regla con filtro de prefijo y sufijo sin tocar el bucket. |
| **Salida estructurada nativa de Bedrock** (`outputConfig.textFormat`) con boto3 | Lo exige el enunciado. Bedrock no admite `minimum`/`maximum`/`minLength` y limita a 16 campos anulables: el esquema para Bedrock se genera aparte (10 anulables, 0 opcionales) y los rangos se validan después con Pydantic. Sin LangChain: menos dependencias y se ve exactamente qué se envía. |
| **Evidencias como texto** (`""` si el valor es null) | Si las evidencias fueran anulables habría 20 campos anulables, por encima del límite de 16. |
| **Aurora Serverless v2 con 0 ACU mínimas + Data API** | Sin VPC en las Lambdas ni contraseñas: IAM + Secrets Manager gestionado por RDS. Se pausa sola cuando no se usa; al despertar (~15 s) el ejecutor reintenta. |
| **Vistas `api_*`** | Desacoplan la API del esquema físico (C4). |
| **PostgreSQL real en los tests** | Los `ON CONFLICT`, `NULLS NOT DISTINCT` y las vistas se prueban con el mismo SQL que corre en Aurora. |

## Observabilidad

- Logs JSON con `correlation_id` (viene de los metadatos de C1 y se propaga al `.md`, al JSON y a `documento`).
- Métricas EMF en `PipelineFondos/Procesamiento`: `Documentos` y `DuracionProceso` por `Etapa` y `Resultado` (`CONVERTIDO`, `OMITIDO`, `VALID`, `REJECTED`, `DUPLICADO`, `ERROR`, `FALLO_INTENTO`...).
- Outputs `dlq_names` para las alarmas de P3.

## Tests

```bash
uv sync --group dev --group test-procesamiento
uv run pytest -q tests/procesamiento        # 40 tests; arranca un PostgreSQL temporal si hay initdb
TEST_DATABASE_URL=postgresql://... uv run pytest -q tests/procesamiento
terraform -chdir=infra/modules/processing test   # proveedor simulado, sin AWS
```

Fixtures: dos KID y una ficha reales de Bestinver, el Markdown del KID de Bestinfond y una respuesta de Bedrock correcta. Casos cubiertos: VALID cargado, reentrega del mensaje, mismo PDF en otra fecha, carga repetida, ficha (no KID), evidencia inventada, rangos, ISIN inválido, error de Bedrock en intento intermedio y último, PDF sin texto, PDF corrupto, clave fuera de contrato, migraciones idempotentes y vistas contra los modelos de la API.

## Despliegue

Workflow `.github/workflows/deploy-processing-dev.yml`: en cada PR, tests con PostgreSQL 16, `terraform validate` y `terraform test`; en `main`, ECR → imagen ARM64 por digest → `terraform apply` de `infra/environments/dev/processing` → migraciones.

## Dependencias con otros frentes (pendiente de acordar)

**P1 (captura):**
1. Escribir en `raw/{gestora}/{AAAAMMDD}/{slug}_{tipo}.pdf` (hoy el scraper escribe sin `raw/`).
2. Activar EventBridge en el bucket (`eventbridge = true` en `aws_s3_bucket_notification`), cifrado, versionado y sin acceso público.
3. Metadatos de C1: `gestora`, `tipo_documento`, `url_origen`, `fecha_descarga`, `sha256`, `correlation_id` (hoy solo `url-origen`). P2 funciona sin ellos, pero se pierde trazabilidad.
4. Aprobar `contracts/events/pdf_created.json` (borrador de P2 como consumidor).

**P3 (plataforma):**
1. Revisar y aplicar `infra/bootstrap/processing_cd_permissions.tf` (permisos de despliegue y permissions boundary de las Lambdas de P2).
2. Repositorio de Aurora en la API: leer de `api_kid_version` y `api_fondo` con la Data API (outputs `database_cluster_arn` y `database_secret_arn`). El rol de la Lambda de la API necesitará `rds-data:ExecuteStatement` y `secretsmanager:GetSecretValue`.
3. Alarmas sobre las DLQ (`dlq_names`).
4. Cambio menor compartido: `modules/container_registry` acepta `component` (por defecto `frontend`, sin efecto en lo existente).

**Equipo:** confirmar el modelo de Bedrock. Por defecto se deja el del script de ejemplo (`global.moonshotai.kimi-k3.1`); hay que comprobar en la consola que está habilitado en la cuenta y que admite salidas estructuradas en eu-west-3.
