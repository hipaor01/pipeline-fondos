"""
Descarga los documentos "Datos fundamentales" (KID) y "Ficha del fondo"
de todos los fondos de inversión de Bestinver y los guarda en S3.

Flujo:
  1. Abre https://www.bestinver.es/fondos-de-inversion/ y lee la lista de
     fondos del footer (XPath /html/body/div[1]/footer/div[2]/div/div[1]/div/ul).
  2. Entra en la página de cada fondo y lee la lista de documentos
     (XPath /html/body/div[1]/div/main/section[4]/div[1]/div[2]/ul).
  3. Descarga los documentos cuyo texto coincide con los buscados y los sube
    a s3://<bucket>/raw/<prefijo>/<AAAAMMDD>/<slug>_<tipo>.pdf.

Las credenciales de AWS se toman de la configuración estándar
(aws configure / aws login, variables de entorno o perfil con AWS_PROFILE).

Uso:
    python descargar_kids_bestinver.py [--bucket curso-miax-pipeline-fondos]
                                       [--prefijo bestinver] [--fecha AAAAMMDD]
                                       [--delay 1.0]
"""

import argparse
import builtins
import hashlib
import io
import json
import re
import sys
import time
import unicodedata
from contextvars import ContextVar
from dataclasses import asdict
from datetime import datetime, timezone
from urllib.parse import quote, urljoin, urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

import boto3
import requests
from botocore.exceptions import BotoCoreError, ClientError
from lxml import html
from pypdf import PdfReader
from pypdf.errors import PdfReadError

if __package__:
    from .base import Documento, Incidencia, ResultadoIngesta, Subida
else:
    from base import Documento, Incidencia, ResultadoIngesta, Subida

BASE_URL = "https://www.bestinver.es/fondos-de-inversion/"

BUCKET_POR_DEFECTO = "curso-miax-pipeline-fondos"
PREFIJO_POR_DEFECTO = "bestinver"

XPATH_LISTA_FONDOS = "/html/body/div[1]/footer/div[2]/div/div[1]/div/ul"
XPATH_LISTA_DOCUMENTOS = "/html/body/div[1]/div/main/section[4]/div[1]/div[2]/ul"

# Texto del enlace (normalizado) -> sufijo del fichero descargado
DOCUMENTOS_OBJETIVO = {
    "datos fundamentales": "datos_fundamentales",
    "ficha del fondo": "ficha_fondo",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}


CORRELATION_ID: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def informar(mensaje: str) -> None:
    correlation_id = CORRELATION_ID.get()
    if correlation_id:
        mensaje = "\n".join(f"[{correlation_id}] {linea}" if linea else "" for linea in mensaje.split("\n"))
    builtins.print(mensaje)


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y con espacios colapsados."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texto).strip().lower()


def obtener_arbol(session: requests.Session, url: str) -> html.HtmlElement:
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return html.fromstring(resp.content)


def obtener_fondos(session: requests.Session) -> list[tuple[str, str]]:
    """Devuelve [(nombre, url)] de los fondos listados en el footer."""
    arbol = obtener_arbol(session, BASE_URL)
    listas = arbol.xpath(XPATH_LISTA_FONDOS)
    if listas:
        enlaces = listas[0].xpath(".//a[@href]")
    else:
        # Respaldo por si cambia la maquetación: enlaces del footer a /fondos-de-inversion/<slug>/
        informar("[aviso] XPath de la lista de fondos no encontrado, usando respaldo.")
        enlaces = arbol.xpath("//footer//a[contains(@href, '/fondos-de-inversion/')]")

    fondos, vistos = [], set()
    for a in enlaces:
        url = urljoin(BASE_URL, a.get("href"))
        nombre = " ".join(a.text_content().split())
        # Solo páginas concretas de fondo (/fondos-de-inversion/<slug>/)
        partes = [p for p in urlparse(url).path.split("/") if p]
        if len(partes) != 2 or partes[0] != "fondos-de-inversion":
            continue
        if url not in vistos:
            vistos.add(url)
            fondos.append((nombre, url))
    return fondos


def obtener_documentos(session: requests.Session, url_fondo: str) -> dict[str, str]:
    """Devuelve {sufijo: url_pdf} con los documentos objetivo del fondo."""
    arbol = obtener_arbol(session, url_fondo)
    listas = arbol.xpath(XPATH_LISTA_DOCUMENTOS)
    if listas:
        enlaces = listas[0].xpath(".//a[@href]")
    else:
        # Respaldo: cualquier enlace a PDF de la página
        informar("    [aviso] XPath de documentos no encontrado, usando respaldo.")
        enlaces = arbol.xpath("//main//a[contains(@href, '.pdf')]")

    encontrados = {}
    for a in enlaces:
        texto = normalizar(a.text_content())
        for objetivo, sufijo in DOCUMENTOS_OBJETIVO.items():
            if texto == objetivo and sufijo not in encontrados:
                encontrados[sufijo] = urljoin(url_fondo, a.get("href"))
    return encontrados


def descargar(session: requests.Session, url: str) -> bytes:
    """Descarga el PDF completo en memoria (son ficheros pequeños)."""
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF-"):
        raise ValueError("La respuesta no empieza con una cabecera PDF válida.")
    try:
        if not PdfReader(io.BytesIO(resp.content), strict=True).pages:
            raise ValueError("El PDF no contiene páginas.")
    except (PdfReadError, OSError, ValueError) as error:
        raise ValueError("La respuesta no contiene un PDF legible.") from error
    return resp.content


def subir_s3(s3, bucket: str, clave: str, contenido: bytes, documento: Documento, fecha_descarga: datetime) -> str | None:
    respuesta = s3.put_object(
        Bucket=bucket,
        Key=clave,
        Body=contenido,
        ContentType="application/pdf",
        Metadata={
            "gestora": documento.gestora,
            "tipo-documento": documento.tipo,
            "url-origen": quote(documento.url, safe=":/?#[]@!$&'()*+,;=%-._~"),
            "fecha-descarga-utc": fecha_descarga.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "sha256": hashlib.sha256(contenido).hexdigest(),
            "correlation-id": CORRELATION_ID.get() or "",
        },
    )
    return respuesta.get("VersionId")


def fecha_valida(texto: str) -> str:
    """Valida el formato AAAAMMDD para argparse."""
    try:
        datetime.strptime(texto, "%Y%m%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"fecha no válida '{texto}', formato AAAAMMDD")
    return texto


class ScraperBestinver:
    """Descubre los documentos de Bestinver sin descargarlos ni subirlos."""

    def __init__(self, session: requests.Session, delay: float = 1.0) -> None:
        self.session = session
        self.delay = delay
        self.fallos: list[Incidencia] = []
        self.ausentes: list[Incidencia] = []

    def descubrir(self) -> list[Documento]:
        self.fallos.clear()
        self.ausentes.clear()
        fondos = obtener_fondos(self.session)
        if not fondos:
            self.fallos.append(Incidencia("listado", "No se encontraron fondos", url=BASE_URL))
        informar(f"Encontrados {len(fondos)} fondos.\n")
        documentos = []
        for nombre, url in fondos:
            slug = [p for p in urlparse(url).path.split("/") if p][-1]
            informar(f"- {nombre} ({url})")
            time.sleep(self.delay)
            try:
                encontrados = obtener_documentos(self.session, url)
            except requests.RequestException as error:
                informar(f"    [error] no se pudo abrir la página: {error}")
                self.fallos.append(Incidencia("pagina", str(error), fondo=nombre, url=url))
                continue
            for sufijo, tipo in (("datos_fundamentales", "kid"), ("ficha_fondo", "ficha_fondo")):
                if sufijo not in encontrados:
                    informar(f"    [sin documento] {sufijo}")
                    self.ausentes.append(Incidencia("ausente", "Documento no encontrado", nombre, tipo, url))
                    continue
                documentos.append(Documento("bestinver", slug, tipo, encontrados[sufijo], nombre))
        return documentos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", default=BUCKET_POR_DEFECTO, help="Bucket de S3 de destino")
    parser.add_argument("--prefijo", default=PREFIJO_POR_DEFECTO, help="Carpeta raíz dentro del bucket")
    parser.add_argument(
        "--fecha", type=fecha_valida, default=None,
        help="Subcarpeta de fecha AAAAMMDD (por defecto, hoy)",
    )
    parser.add_argument("--delay", type=float, default=1.0, help="Segundos de espera entre peticiones")
    parser.add_argument("--correlation-id", default=None, help="Identificador de la ejecución")
    args = parser.parse_args()
    correlation_id = args.correlation_id or str(uuid4())
    if len(correlation_id) > 128 or not correlation_id.isascii() or not correlation_id.isprintable():
        parser.error("El correlation-id debe ser ASCII imprimible y tener hasta 128 caracteres")
    token = CORRELATION_ID.set(correlation_id)
    try:
        resultado = ejecutar(args)
        return 0 if resultado.estado == "completa" else 1
    finally:
        CORRELATION_ID.reset(token)


def ejecutar(args: argparse.Namespace) -> ResultadoIngesta:
    resultado = ResultadoIngesta()
    inicio = datetime.now(timezone.utc)
    intento = str(uuid4())
    fecha = args.fecha or datetime.now(ZoneInfo("Europe/Madrid")).strftime("%Y%m%d")
    carpeta_s3 = f"raw/{args.prefijo.strip('/')}/{fecha}"
    s3 = boto3.client("s3")
    try:
        s3.head_bucket(Bucket=args.bucket)
        if s3.get_bucket_versioning(Bucket=args.bucket).get("Status") != "Enabled":
            resultado.fallos.append(Incidencia("versionado", "El bucket no tiene el versionado activado"))
            informar("[error] el bucket no tiene el versionado activado")
            return resultado
    except (BotoCoreError, ClientError) as e:
        informar(f"[error] no se puede acceder al bucket '{args.bucket}': {e}")
        resultado.fallos.append(Incidencia("bucket", str(e)))
        return resultado
    informar(f"Destino: s3://{args.bucket}/{carpeta_s3}/\n")

    session = requests.Session()
    session.headers.update(HEADERS)

    scraper = ScraperBestinver(session, args.delay)
    try:
        documentos = scraper.descubrir()
    except requests.RequestException as error:
        informar(f"[error] no se pudo consultar el listado: {error}")
        resultado.fallos.append(Incidencia("listado", str(error), url=BASE_URL))
        documentos = []
    resultado.fallos.extend(scraper.fallos)
    resultado.ausentes.extend(scraper.ausentes)
    claves_vistas = set()
    for documento in documentos:
        nombre = documento.nombre_fondo
        sufijo = documento.tipo
        clave = f"{carpeta_s3}/{documento.slug}_{sufijo}.pdf"
        if clave in claves_vistas:
            informar(f"    [error] clave S3 duplicada: {clave}")
            resultado.fallos.append(Incidencia("clave_duplicada", clave, nombre, sufijo, documento.url))
            continue
        claves_vistas.add(clave)
        try:
            time.sleep(args.delay)
            contenido = descargar(session, documento.url)
            fecha_descarga = datetime.now(timezone.utc)
        except (requests.RequestException, ValueError) as e:
            informar(f"    [error] descarga {sufijo}: {e}")
            resultado.fallos.append(Incidencia("descarga", str(e), nombre, sufijo, documento.url))
            continue
        try:
            version = subir_s3(s3, args.bucket, clave, contenido, documento, fecha_descarga)
            informar(f"    [ok] s3://{args.bucket}/{clave}")
            resultado.subidos.append(Subida(documento, args.bucket, clave, version, hashlib.sha256(contenido).hexdigest(), fecha_descarga.isoformat().replace("+00:00", "Z")))
            if not version or version == "null":
                resultado.fallos.append(Incidencia("version_s3", "Subida sin versionId; comprobar versionado del bucket", nombre, sufijo, documento.url, clave))
        except (BotoCoreError, ClientError) as e:
            informar(f"    [error] subida {sufijo}: {e}")
            resultado.fallos.append(Incidencia("subida_resultado_incierto", str(e), nombre, sufijo, documento.url, clave, hashlib.sha256(contenido).hexdigest()))

    manifiesto = {
        "schema_version": "1.0",
        "execution_id": CORRELATION_ID.get(),
        "attempt_id": intento,
        "gestora": "bestinver",
        "inicio_utc": inicio.isoformat().replace("+00:00", "Z"),
        "fin_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "estado": resultado.estado,
        "contadores": {"subidos": len(resultado.subidos), "ausentes": len(resultado.ausentes), "fallos": len(resultado.fallos)},
        "subidos": [asdict(subida) for subida in resultado.subidos],
        "ausentes": [asdict(ausente) for ausente in resultado.ausentes],
        "fallos": [asdict(fallo) for fallo in resultado.fallos],
    }
    identificador = CORRELATION_ID.get() or intento
    clave_ejecucion = hashlib.sha256(identificador.encode("utf-8")).hexdigest()
    clave_manifiesto = f"manifests/bestinver/{fecha}/{clave_ejecucion}/{intento}.json"
    try:
        s3.put_object(Bucket=args.bucket, Key=clave_manifiesto, Body=json.dumps(manifiesto, ensure_ascii=False).encode("utf-8"), ContentType="application/json")
        informar(f"Manifiesto: s3://{args.bucket}/{clave_manifiesto}")
    except (BotoCoreError, ClientError) as error:
        informar(f"[error] no se pudo guardar el manifiesto: {error}")
        resultado.fallos.append(Incidencia("manifiesto_resultado_incierto", str(error), clave=clave_manifiesto))
    informar(f"\nSubidos {len(resultado.subidos)} documentos a 's3://{args.bucket}/{carpeta_s3}/'.")
    informar(f"Estado: {resultado.estado}; fallos: {len(resultado.fallos)}")
    for fallo in resultado.fallos:
        informar(f"  - {fallo.etapa}: {fallo.mensaje}")
    return resultado


if __name__ == "__main__":
    sys.exit(main())
