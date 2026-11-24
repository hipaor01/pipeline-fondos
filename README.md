# pipeline-fondos

Proyecto para extraer información de los KID (Documento de Datos Fundamentales) y fichas de fondos de inversión.

La primera etapa del pipeline descarga, mediante web scraping, los documentos de **Bestinver, Azvalor y Cobas AM** y los guarda en **Amazon S3**.

Para preparar un bucket de pruebas en una cuenta propia y entender las decisiones
de captura, consulta la [guía AWS de captura](documentacion/GUIA_AWS_CAPTURA.md).
La [guía de automatización P1](documentacion/AUTOMATIZACION_P1.md) describe el
empaquetado y el despliegue de prueba con Lambda, Step Functions y Scheduler.
La raíz Terraform de [almacenamiento P1](infra/environments/dev/storage/README.md)
permite crear un bucket nuevo o referenciar uno ya existente sin modificarlo.

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
uv run --group scraping python webscrapper/descargar_kids_bestinver.py --correlation-id mi-ejecucion
```

### Cómo se analizó la web

1. **Listado de fondos.** En `https://www.bestinver.es/fondos-de-inversion/` el pie de página contiene una lista con todos los productos. La lista de fondos de inversión está en el XPath:

   ```
   /html/body/div[1]/footer/div[2]/div/div[1]/div/ul
   ```

   Los enlaces llevan a fondos o a categorías como `otros` y `sicav-luxemburguesas`; estas últimas enlazan a productos en rutas más profundas.

2. **Documentos de cada fondo.** En la página de cada fondo hay una lista de documentos (datos fundamentales, ficha, folleto, reglamento, cuentas anuales, informes semestrales...) en el XPath:

   ```
   /html/body/div[1]/div/main/section[3]/div[1]/div[2]/ul
   ```

   Los enlaces apuntan directamente a PDFs en `/wp-content/uploads/`, por ejemplo
   `bestinfond_fi_datos_fundamentales.pdf`.

3. **Documentos que se descargan:** solo **"Datos fundamentales"** (KID) y **"Ficha del fondo"**.

Las páginas son HTML estático (no necesitan JavaScript), así que basta con `requests` + `lxml`; no hace falta Selenium ni Playwright.

### Qué hace el script

1. Extrae los enlaces HTTPS del dominio de Bestinver desde el footer. Si una página sin documentos enlaza a productos bajo su propia ruta, sigue esos enlaces como categoría y procesa cada producto una sola vez.
2. Para cada fondo, abre su página y busca los enlaces cuyo texto normalizado es `datos fundamentales` o `ficha del fondo`. Si aparecen dos URLs distintas del mismo tipo, registra la ambigüedad sin elegir una.
3. Comprueba al inicio que el bucket es accesible (si no, termina con error).
4. Descarga cada PDF en memoria y lo sube a S3 con `ContentType: application/pdf` y metadatos de procedencia, fecha UTC, SHA-256 y correlación. Si se relanza el mismo día, se escribe la misma clave; con versionado activo se crea una nueva versión.
5. Muestra un resumen con los documentos descargados y los fallos.

Antes de la subida se comprueba la cabecera y se abre el PDF con `pypdf` para
rechazar respuestas vacías, HTML o documentos que no se puedan leer. Si dos
documentos de una ejecución generan la misma clave S3, se informa el conflicto
y no se sobrescribe el primero.
Cada ejecución genera un identificador de correlación, salvo que se facilite uno
con `--correlation-id`; aparece en los mensajes y en los metadatos de S3.
El resultado distingue ejecuciones completas, parciales y fallidas; la CLI
devuelve un código distinto de cero si hay fallos o no se sube ningún documento.
Las fichas ausentes se registran por separado; un KID ausente se registra además
como fallo para que la captura quede parcial o fallida.
Se guarda un manifiesto JSON por intento bajo `manifests/bestinver/`, con las
subidas, versiones S3, huellas, ausencias y fallos. Un error al guardar el
manifiesto se refleja en el resultado. Una interrupción abrupta puede dejar
objetos sin manifiesto y requiere conciliarlos mediante S3 y los logs. El bucket
debe tener el versionado activado; una subida sin versión se informa como fallo.
La fecha de cada clave corresponde a la descarga en Madrid, salvo que `--fecha`
la fije de forma explícita; el manifiesto usa la fecha de inicio del intento.
El scraper comprueba el versionado antes de subir, por lo que necesita también
`s3:GetBucketVersioning` en el bucket.
Repetir una captura puede crear nuevas versiones físicas incluso si los bytes
no cambian. El hash permite reconocer el contenido repetido, pero la deduplicación
lógica y la conservación de las procedencias corresponden al procesamiento P2;
todavía no están implementadas en este repositorio.

**Respaldo:** si el bloque principal no contiene fondos o falta algún tipo de documento, el script usa un selector más general (enlaces del footer a `/fondos-de-inversion/` o enlaces a `.pdf` dentro de `<main>`) y muestra un aviso.

### Salida

```
s3://curso-miax-pipeline-fondos/
└── raw/bestinver/
    └── 20261119/
        ├── bestinfond_kid.pdf
        ├── bestinfond_ficha_fondo.pdf
        ├── bestinver-internacional_kid.pdf
        └── ...
```

Cada ejecución guarda los documentos en una carpeta con la fecha de Madrid (`AAAAMMDD`). Nombre de cada fichero: `<slug-del-fondo>_<tipo>.pdf`, con tipos `kid` y `ficha_fondo`. Los objetos anteriores permanecen en sus rutas originales.

### Resultados (ejecución del 19/11/2026)

- 24 enlaces en el footer, 22 de ellos fondos con documentos.
- **37 PDFs** subidos a `s3://curso-miax-pipeline-fondos/bestinver/20261119/`: 22 "Datos fundamentales" y 15 "Fichas del fondo".
- Sin ficha publicada en la web: Latam, Solidario y Bonos Institucional I–V.
- `Otros` y `SICAV Luxemburguesas` son páginas que agrupan varios productos y no tienen estos documentos.

## Etapa 1: descarga de documentos de Azvalor

Script: [`webscrapper/descargar_kids_azvalor.py`](webscrapper/descargar_kids_azvalor.py).

Descubre los fondos de inversión y las SICAV o clases enlazados en el menú de
`https://www.azvalor.com/fondos-de-inversion/`. Identifica por el texto del
enlace el **Folleto simplificado (DFP)** o **Documento de datos fundamentales**
como KID y la ficha de producto como `ficha_fondo`. Mantiene claves diferentes
para cada clase, incluso si comparten la misma ficha. Si encuentra varios KID
distintos para un producto, informa un fallo en lugar de elegir uno al azar.

```bash
uv run --group scraping python webscrapper/descargar_kids_azvalor.py --bucket mi-bucket
uv run --group scraping python webscrapper/descargar_kids_azvalor.py --bucket mi-bucket --fecha 20261123 --delay 1 --correlation-id prueba-azvalor
```

Comparte con Bestinver la validación PDF, el versionado, los metadatos y el
manifiesto. Las claves son `raw/azvalor/AAAAMMDD/<slug>_<tipo>.pdf` y el
manifiesto se guarda bajo `manifests/azvalor/`. En la prueba real del 23/11/2026
se encontraron **11 KID y 10 fichas**; la página de Capital FI no enlazaba una
ficha de producto. La estructura y los documentos pueden cambiar.

## Etapa 1: descarga de documentos de Cobas AM

Script: [`webscrapper/descargar_kids_cobas.py`](webscrapper/descargar_kids_cobas.py).

Descubre los productos de inversión enlazados desde `https://www.cobasam.com/productos/`
y extrae el enlace `PRIIP pdf` y la `Ficha del fondo pdf` de cada bloque de
producto o clase. Conserva el ISIN y la clase de cada bloque; las claves de
clase incluyen un sufijo como `-clase-a`. No selecciona arbitrariamente un
enlace o una clase si existen varios candidatos incompatibles. Los planes de
pensiones quedan fuera del alcance de esta captura de fondos de inversión.

```bash
uv run --group scraping python webscrapper/descargar_kids_cobas.py --bucket mi-bucket
uv run --group scraping python webscrapper/descargar_kids_cobas.py --bucket mi-bucket --fecha 20261123 --delay 1 --correlation-id prueba-cobas
```

Las claves son `raw/cobas/AAAAMMDD/<slug>_<tipo>.pdf` y el manifiesto se
guarda bajo `manifests/cobas/`. En la prueba real del 23/11/2026 se capturaron
22 KID y 22 fichas correspondientes a siete productos y sus clases.

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

El frontend Streamlit se ejecuta en otra terminal desde la raíz del repositorio:

```bash
uv run --group frontend python -m streamlit run frontend/app.py
```

Se usa `python -m streamlit` para conservar la raíz del repositorio en la ruta
de importación de Python. Por defecto, el frontend consulta la API en
`http://localhost:8000`; se puede cambiar mediante `API_BASE_URL`.

### Contenedor local del frontend

La imagen se construye para Linux ARM64, la misma arquitectura que se usará en
ECS sobre AWS Graviton. Ejecuta Streamlit como un usuario sin privilegios y
publica el puerto `8501`. Para construirla y conectarla con la API que se
ejecuta en el host:

```bash
docker buildx build \
  --platform linux/arm64 \
  --load \
  -t pipeline-fondos-frontend:local \
  .
docker run --rm \
  --name pipeline-fondos-frontend \
  -p 8501:8501 \
  -e API_BASE_URL=http://host.docker.internal:8000 \
  pipeline-fondos-frontend:local
```

La aplicación queda disponible en `http://localhost:8501`. Su comprobación de
salud ligera, que no consulta la API ni otras dependencias, está en:

```bash
curl --fail http://localhost:8501/_stcore/health
docker inspect \
  --format '{{.State.Health.Status}}' \
  pipeline-fondos-frontend
```

En ECS Express Mode se debe seleccionar explícitamente la arquitectura `ARM64`,
ya que `X86_64` es la opción predeterminada. También se debe configurar el puerto
del contenedor como `8501` y el health check del balanceador como
`/_stcore/health`. El `HEALTHCHECK` de la imagen sirve para Docker local, pero
ECS solo informa de la salud del contenedor si el mismo comando se declara
posteriormente en la definición de tarea.

### Publicación del frontend en ECR

El workflow [`.github/workflows/publish-frontend-dev.yml`](.github/workflows/publish-frontend-dev.yml)
valida el frontend y Terraform en cada pull request. Cuando los cambios llegan
a `main`, utiliza un runner ARM64 nativo para:

- crear o actualizar el repositorio privado `pipeline-fondos-dev-frontend`;
- construir la imagen para `linux/arm64`;
- etiquetarla con el SHA completo e inmutable del commit;
- publicarla en ECR;
- desplegar ese digest en ECS Express Mode y comprobar su endpoint público.

Antes de la primera ejecución hay que volver a aplicar `infra/bootstrap` para
ampliar los permisos del rol OIDC al nuevo estado y al repositorio ECR:

```bash
terraform -chdir=infra/bootstrap init \
  -backend-config="bucket=pipeline-fondos-terraform-state-065451207233"
terraform -chdir=infra/bootstrap plan
terraform -chdir=infra/bootstrap apply
```

Las etiquetas del repositorio son inmutables, las imágenes se escanean al
publicarse y una política de ciclo de vida conserva únicamente las 30 más
recientes. Si se reejecuta la pipeline para un SHA ya publicado, reutiliza esa
imagen en lugar de intentar sobrescribirla.

### Despliegue en ECS Express Mode

El servicio se gestiona desde `infra/environments/dev/frontend-service`, con un
estado independiente del repositorio ECR. Utiliza Linux ARM64 sobre Graviton,
0,5 vCPU y 1 GiB de memoria por tarea, y escala entre una y dos tareas según el
uso medio de CPU. ECS Express administra el balanceador, TLS, red y endpoint
público sobre la VPC predeterminada de `eu-west-3`.

Streamlit escucha en el puerto `8501`; el balanceador consulta
`/_stcore/health`. La variable `API_BASE_URL` se obtiene del estado Terraform de
la API y los logs se conservan 14 días en CloudWatch. Cada despliegue utiliza la
imagen por digest, nunca una etiqueta mutable.

Para evitar el coste fijo cuando no se utiliza el entorno, el workflow manual
`Manage frontend service in dev` permite ejecutar `start` o `stop` desde la rama
`main`. `start` despliega el último digest etiquetado disponible en ECR y
comprueba el health check. `stop` exige confirmar la interrupción y destruye
únicamente el root `frontend-service`; conserva la API, ECR, los artefactos y el
backend de Terraform. Un despliegue posterior del frontend a `main` volverá a
crear el servicio aunque se hubiera detenido manualmente.

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
