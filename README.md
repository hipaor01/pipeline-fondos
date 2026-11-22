# pipeline-fondos

Proyecto para extraer información de los KID (Documento de Datos Fundamentales) y fichas de fondos de inversión.

La primera etapa del pipeline descarga, mediante web scraping, los documentos de los fondos de **Bestinver** y los guarda en **Amazon S3**.

## Instalación

```bash
uv sync --group dev
```

`uv` crea y mantiene automáticamente el entorno `.venv` a partir de
`pyproject.toml` y `uv.lock`. Los grupos disponibles son:

- `dev`: API, tests, Uvicorn, Ruff y mypy; recomendado para trabajar en la API.
- `api`: dependencias mínimas de FastAPI y Mangum para la Lambda.
- `scraping`: descarga de documentos y acceso a S3.
- `procesamiento`: conversión PDF a Markdown y OCR.
- `extraccion`: extracción estructurada mediante Bedrock.

Para preparar únicamente otra etapa, se puede ejecutar, por ejemplo,
`uv sync --group scraping`. `uv sync --all-groups` instala el entorno completo.

### Credenciales de AWS

El script usa la cadena de credenciales estándar de AWS: `aws login` / `aws configure`, variables de entorno (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) o un perfil con `AWS_PROFILE`. La cuenta necesita permisos `s3:PutObject` y `s3:ListBucket` sobre el bucket `curso-miax-pipeline-fondos`.

## Etapa 1: descarga de documentos de Bestinver

Script: [`descargar_kids_bestinver.py`](descargar_kids_bestinver.py)

```bash
uv run --group scraping python webscrapper/descargar_kids_bestinver.py
uv run --group scraping python webscrapper/descargar_kids_bestinver.py --fecha 20261119
uv run --group scraping python webscrapper/descargar_kids_bestinver.py --bucket otro-bucket
uv run --group scraping python webscrapper/descargar_kids_bestinver.py --prefijo pruebas
uv run --group scraping python webscrapper/descargar_kids_bestinver.py --delay 0.5
```

### Cómo se analizó la web

1. **Listado de fondos.** En `https://www.bestinver.es/fondos-de-inversion/` el pie de página contiene una lista con todos los productos. La lista de fondos de inversión está en el XPath:

   ```
   /html/body/div[1]/footer/div[2]/div/div[1]/div/ul
   ```

   Cada enlace lleva a la página del fondo: `/fondos-de-inversion/<slug>/`.

2. **Documentos de cada fondo.** En la página de cada fondo hay una lista de documentos (datos fundamentales, ficha, folleto, reglamento, cuentas anuales, informes semestrales...) en el XPath:

   ```
   /html/body/div[1]/div/main/section[4]/div[1]/div[2]/ul
   ```

   Los enlaces apuntan directamente a PDFs en `/wp-content/uploads/`, por ejemplo
   `bestinfond_fi_datos_fundamentales.pdf`.

3. **Documentos que se descargan:** solo **"Datos fundamentales"** (KID) y **"Ficha del fondo"**.

Las páginas son HTML estático (no necesitan JavaScript), así que basta con `requests` + `lxml`; no hace falta Selenium ni Playwright.

### Qué hace el script

1. Descarga la página de listado y extrae los enlaces de la lista del footer (XPath anterior). Se queda solo con URLs del tipo `/fondos-de-inversion/<slug>/`.
2. Para cada fondo, abre su página, localiza la lista de documentos y selecciona los enlaces cuyo texto (normalizado: minúsculas, sin acentos) es exactamente `datos fundamentales` o `ficha del fondo`.
3. Comprueba al inicio que el bucket es accesible (si no, termina con error).
4. Descarga cada PDF en memoria y lo sube a S3 con `ContentType: application/pdf` y la URL original en los metadatos (`x-amz-meta-url-origen`). Si se relanza el mismo día, los objetos se sobrescriben.
5. Muestra un resumen con los documentos descargados y los fallos.

**Respaldo:** si un XPath deja de encontrar nada (porque cambie la maquetación de la web), el script usa un selector más general (enlaces del footer a `/fondos-de-inversion/` o enlaces a `.pdf` dentro de `<main>`) y muestra un aviso.

### Salida

```
s3://curso-miax-pipeline-fondos/
└── bestinver/
    └── 20261119/
        ├── bestinfond_datos_fundamentales.pdf
        ├── bestinfond_ficha_fondo.pdf
        ├── bestinver-internacional_datos_fundamentales.pdf
        └── ...
```

Cada ejecución guarda los documentos en una carpeta con la fecha (`AAAAMMDD`), así se conserva el histórico de versiones de los KID. Nombre de cada fichero: `<slug-del-fondo>_<tipo>.pdf`.

### Resultados (ejecución del 19/11/2026)

- 24 enlaces en el footer, 22 de ellos fondos con documentos.
- **37 PDFs** subidos a `s3://curso-miax-pipeline-fondos/bestinver/20261119/`: 22 "Datos fundamentales" y 15 "Fichas del fondo".
- Sin ficha publicada en la web: Latam, Solidario y Bonos Institucional I–V.
- `Otros` y `SICAV Luxemburguesas` son páginas que agrupan varios productos y no tienen estos documentos.

## Etapa 2: transformación de PDF a Markdown

Script: [`structured_output/pdf_a_markdown.py`](structured_output/pdf_a_markdown.py)

Convierte los PDF a Markdown con [PyMuPDF](https://pymupdf.readthedocs.io/) (`pymupdf4llm`), que conserva títulos, listas y **tablas** (las de costes y rentabilidades salen como tablas Markdown) y aplica **OCR** con RapidOCR en las páginas que lo necesitan. RapidOCR forma parte del grupo `procesamiento`; si no está disponible, `pymupdf4llm` usa Tesseract si lo encuentra instalado.

```bash
uv run --group procesamiento python structured_output/pdf_a_markdown.py
uv run --group procesamiento python structured_output/pdf_a_markdown.py ruta/fichero.pdf
uv run --group procesamiento python structured_output/pdf_a_markdown.py --salida markdown/
uv run --group procesamiento python structured_output/pdf_a_markdown.py --ocr siempre
uv run --group procesamiento python structured_output/pdf_a_markdown.py --sobrescribir
```

Cada `<slug>_<tipo>.pdf` genera un `<slug>_<tipo>.md`. Termina con un resumen de convertidos, omitidos y fallos. El OCR tarda unos segundos por página.

## Etapa 3: extracción de datos del KID

Script: [`structured_output/ejemplo_kid.py`](structured_output/ejemplo_kid.py)

Lee el Markdown de un KID (generado en la etapa 2) y extrae con un LLM en Amazon Bedrock (salida estructurada con Pydantic) el ISIN, nombre, gestora, SRI, periodo de mantenimiento y costes, cada uno con su **evidencia** literal. Después comprueba que cada evidencia aparece en el documento (ignorando la marca Markdown y los espacios).

```bash
uv run --group extraccion python structured_output/ejemplo_kid.py
uv run --group extraccion python structured_output/ejemplo_kid.py descargas/bestinver/bestinver-renta_datos_fundamentales.md
```

## Contrato de la API

La especificación OpenAPI se encuentra en
[`contracts/openapi/api.yaml`](contracts/openapi/api.yaml). Define los endpoints
mínimos `GET /health`, `GET /gestoras`, `GET /fondos`, `GET /fondos/{isin}` y
`GET /kids`, junto con sus filtros, paginación, modelos de respuesta y errores.

Los modelos Pydantic están en `api/models/`. La interfaz de solo lectura
`RepositorioFondos`, situada en `api/repositories/base.py`, desacopla la API de
la implementación de acceso a Aurora y permite utilizar repositorios simulados
en las pruebas.

`RepositorioFondosEnMemoria.con_datos_semilla()` proporciona una implementación
determinista para desarrollo local. Respeta los mismos filtros, ordenación y
paginación que deberá implementar el repositorio de Aurora.

`ServicioFondos`, en `api/services/fondos.py`, convierte los resultados del
repositorio en respuestas Pydantic y representa un ISIN inexistente mediante la
excepción de negocio `FondoNoEncontrado`.

La aplicación FastAPI está en `api/app.py`. Por defecto utiliza el repositorio
en memoria y puede ejecutarse localmente con:

```bash
uv run --group dev uvicorn api.app:app --reload
```

En AWS Lambda, el adaptador Mangum expone la misma aplicación mediante el
handler `api.lambda_handler.handler`. Está configurado para eventos de API
Gateway HTTP API v2 y no ejecuta el ciclo de vida ASGI, ya que actualmente la
aplicación no tiene tareas de inicio o cierre.

Para exportar únicamente las dependencias de esta Lambda durante el build:

```bash
uv export --only-group api --no-emit-project --locked --output-file build/requirements-api.txt
```

## Despliegue continuo de la API

El workflow [`.github/workflows/deploy-api-dev.yml`](.github/workflows/deploy-api-dev.yml)
valida el proyecto en cada pull request y despliega `dev` cuando los cambios
llegan a `main`. Se autentica en AWS mediante OIDC, sin claves estáticas.

Antes del primer despliegue hay que aplicar manualmente `infra/bootstrap` y
guardar el ARN resultante como variable del repositorio:

```bash
terraform -chdir=infra/bootstrap apply
gh variable set AWS_DEPLOY_ROLE_ARN \
  --body "$(terraform -chdir=infra/bootstrap output -raw github_actions_cd_role_arn)"
```

La pipeline crea el bucket versionado de artefactos, construye un ZIP Linux
`x86_64` únicamente con el grupo `api`, lo publica en S3, aplica Terraform y
comprueba el endpoint `/health`. No requiere un GitHub Environment llamado
`dev`; la confianza OIDC está restringida directamente a la rama `main`.

## Próximas etapas

- [x] Extraer información de los KID descargados (PDF → Markdown → datos estructurados).
- [ ] Leer los PDF de S3 y guardar los Markdown y los datos extraídos.
- [ ] Añadir otras gestoras.
