# Procesamiento y datos (P2)

PDF del KID en S3 → Markdown → datos estructurados con Amazon Bedrock → Aurora PostgreSQL.

```
S3 raw/{gestora}/{AAAAMMDD}/{slug}_kid.pdf                            (C1 v1, lo escribe P1)
  │  notificación S3 ObjectCreated, filtro raw/ + _kid.pdf
  ▼
SQS pdf-markdown (DLQ tras 3 intentos) ─► Lambda pdf-markdown (batch=1, máx. 2 en paralelo)
  │                                         pymupdf4llm, sin OCR por defecto
  ▼
S3 processed/markdown/{gestora}/{AAAAMMDD}/{slug}_{tipo}.md            (C2)
  │  notificación S3 ObjectCreated, filtro processed/markdown/ + .md
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
- **Procedencia**: cada objeto exacto `(bucket, key, versionId)` queda en `documento_observacion`, también si el contenido ya estaba cargado.
- **Aurora**: `documento.sha256` único y `kid_version` única por `(isin, fecha_documento, documento_id)` con `NULLS NOT DISTINCT`; todos los `INSERT` usan `ON CONFLICT` y van en una transacción.

## Base de datos (contrato C4)

Migraciones en `database/migrations/`: tablas `gestora`, `fondo`, `clase_fondo`, `documento`, `kid_version` y dos vistas de lectura para la API:

- `api_kid_version`: una fila por versión de KID, con las columnas de `api/models/kid.py`.
- `api_fondo`: el KID más reciente de cada ISIN, con las columnas de `api/models/fondo.py`.

`0003_observaciones.sql` añade `documento_observacion` (procedencias de C1 v1).

El ejecutor de tests envía cada parámetro con el mismo tipo que la Data API (texto como `varchar`, etc.): si falta un `CAST` en el SQL, el test falla igual que fallaría en Aurora.

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
| **Notificación nativa S3 → SQS** | Es el transporte que fija C1 v1. La configuración de notificaciones del bucket es un único recurso y, según la propuesta de integración, la gestiona P2 (estado `dev/processing`). Si alguna vez hiciera falta otro consumidor, se cambiaría a EventBridge (el parser ya acepta ese formato). |
| **Contrato C1 comprobado al entrar** | Metadatos obligatorios y SHA-256 de la versión exacta del evento. Si fallan, `REJECTED` sin reintento. |
| **Procedencias en `documento_observacion`** | C1 pide conservar cada observación aunque el contenido ya exista: el PDF se guarda una vez y cada (bucket, key, versionId) queda registrado. |
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
uv run pytest -q tests/procesamiento        # 48 tests; arranca un PostgreSQL temporal si hay initdb
TEST_DATABASE_URL=postgresql://... uv run pytest -q tests/procesamiento
terraform -chdir=infra/modules/processing test   # proveedor simulado, sin AWS
```

Fixtures: dos KID y una ficha reales de Bestinver, el Markdown del KID de Bestinfond y una respuesta de Bedrock correcta. Casos cubiertos: VALID cargado, reentrega del mensaje, mismo PDF en otra fecha, carga repetida, ficha (no KID), evidencia inventada, rangos, ISIN inválido, error de Bedrock en intento intermedio y último, PDF sin texto, PDF corrupto, clave fuera de contrato, migraciones idempotentes y vistas contra los modelos de la API.

## Despliegue

Workflow reutilizable `.github/workflows/deploy-processing-dev.yml`: en cada PR,
tests con PostgreSQL 16, `terraform validate` y `terraform test`. En `main`, el
orquestador `.github/workflows/deploy-backend-dev.yml` lo invoca antes que el API:
ECR → imagen ARM64 por digest → `terraform apply` de
`infra/environments/dev/processing` → migraciones.

## Integración con P1 y P3

La respuesta de P2 al contrato C1 v1 de P1, con los casos de idempotencia y los límites conocidos, está en [`contracts/C1_RESPUESTA_P2.md`](../contracts/C1_RESPUESTA_P2.md).

Antes del primer despliegue en `main`:

1. **P3** aplica `infra/bootstrap` con `processing_cd_permissions.tf`, que reutiliza `capture_documents_bucket`.
2. **El equipo confirma** que nadie más declara `aws_s3_bucket_notification` para el bucket: el estado de P2 **reemplaza la configuración completa**. El workflow deja la configuración anterior en el resumen.
3. El workflow usa las variables de repositorio `AWS_DEPLOY_ROLE_ARN` y `CAPTURE_DOCUMENTS_BUCKET`, las mismas que la captura.
4. El Scheduler de captura se activa después de que existan las colas y la notificación.
5. **P3**: el repositorio de Aurora de la API lee `api_kid_version` y `api_fondo` con la Data API (outputs `database_cluster_arn` y `database_secret_arn`) y monta las alarmas de las DLQ (`dlq_names`).
6. **Equipo**: confirmar el modelo de Bedrock. Por defecto queda el del script de ejemplo (`global.moonshotai.kimi-k3.1`), sin verificar en la cuenta; hay que comprobar en la consola que está habilitado y admite salidas estructuradas en eu-west-3.
