# CLAUDE.md

Guía para Claude Code en este repositorio.

## Proyecto

Pipeline para descargar y extraer información de los KID (Documento de Datos Fundamentales) y fichas de fondos de inversión. Proyecto del curso MIAX 2026. Ver `README.md` para el detalle de cada etapa.

## Entorno

- Python 3.14 y `uv`; el entorno `.venv/` no se versiona.
- Dependencias y grupos en `pyproject.toml`; `uv.lock` sí se versiona.
- Añadir dependencias con `uv add --group <grupo> <paquete>`.
- Ejecutar desde la raíz con `uv run --group <grupo> python <script>.py`.

## Estructura

- `webscrapper/descargar_kids_bestinver.py`: etapa 1, scraping de los PDF de Bestinver (datos fundamentales y ficha del fondo).
- Almacenamiento: los PDFs se suben a S3, bucket `curso-miax-pipeline-fondos`, con claves `<gestora>/<AAAAMMDD>/<slug>_<tipo>.pdf` (`boto3`, credenciales estándar de AWS). `descargas/` queda en `.gitignore` por si se guarda algo en local.

## Convenciones

- Código, comentarios, mensajes de consola y documentación en **español**.
- Scraping: `requests` + `lxml` con XPath mientras las webs sean HTML estático. Solo usar Selenium/Playwright si la página necesita JavaScript.
- Cada scraper:
  - usa los XPath encontrados en la web como selector principal, con un selector más general de respaldo que avisa por consola;
  - identifica los documentos por el texto del enlace normalizado (minúsculas, sin acentos);
  - deja una pausa entre peticiones (`--delay`) y envía un User-Agent de navegador;
  - sube los ficheros a S3 y acepta `--bucket`, `--prefijo` (por defecto, la gestora) y `--fecha` (AAAAMMDD, por defecto hoy);
  - nombra los ficheros `<slug-del-fondo>_<tipo>.pdf`;
  - termina con un resumen de subidas y fallos.
- Una nueva gestora va en su propio script `descargar_kids_<gestora>.py` y se documenta en el README como una sección nueva.

## Al terminar un cambio

- Actualizar `README.md` si cambia el uso, la salida o se añade una etapa.
- No hacer commit salvo que se pida.
