"""Descarga, trazabilidad y almacenamiento compartidos por los scrapers."""

import argparse
import builtins
import hashlib
import io
import json
import re
import time
import unicodedata
from contextvars import ContextVar
from dataclasses import asdict
from datetime import datetime, timezone
from urllib.parse import quote
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
    return html.fromstring(resp.content, parser=html.HTMLParser(encoding=resp.encoding))

def descargar(session: requests.Session, url: str) -> bytes:
    """Descarga el PDF completo en memoria (son ficheros pequeños)."""
    resp = session.get(url, timeout=60)
    resp.raise_for_status()
    if not resp.content.startswith(b"%PDF-"):
        raise ValueError("La respuesta no empieza con una cabecera PDF válida.")
    try:
        if not PdfReader(io.BytesIO(resp.content), strict=False).pages:
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

def ejecutar(args: argparse.Namespace, scraper_cls, gestora: str, url_listado: str) -> ResultadoIngesta:
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

    scraper = scraper_cls(session, args.delay)
    try:
        documentos = scraper.descubrir()
    except requests.RequestException as error:
        informar(f"[error] no se pudo consultar el listado: {error}")
        resultado.fallos.append(Incidencia("listado", str(error), url=url_listado))
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
        "gestora": gestora,
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
    clave_manifiesto = f"manifests/{gestora}/{fecha}/{clave_ejecucion}/{intento}.json"
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
