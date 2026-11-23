"""
Descarga los documentos "Datos fundamentales" (KID) y "Ficha del fondo"
de todos los fondos de inversión de Bestinver y los guarda en S3.

Flujo:
  1. Abre https://www.bestinver.es/fondos-de-inversion/ y lee la lista de
     fondos del footer (XPath /html/body/div[1]/footer/div[2]/div/div[1]/div/ul).
  2. Entra en la página de cada fondo y lee la lista de documentos
     (XPath /html/body/div[1]/div/main/section[3]/div[1]/div[2]/ul).
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
import sys
import time
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import requests

if __package__:
    from .base import Documento, Incidencia, ResultadoIngesta
    from .ingesta import (
        CORRELATION_ID,
        fecha_valida,
        informar,
        normalizar,
        obtener_arbol,
    )
    from .ingesta import ejecutar as ejecutar_ingesta
else:
    from base import Documento, Incidencia, ResultadoIngesta
    from ingesta import (
        CORRELATION_ID,
        fecha_valida,
        informar,
        normalizar,
        obtener_arbol,
    )
    from ingesta import ejecutar as ejecutar_ingesta

BASE_URL = "https://www.bestinver.es/fondos-de-inversion/"

BUCKET_POR_DEFECTO = "curso-miax-pipeline-fondos"
PREFIJO_POR_DEFECTO = "bestinver"

XPATH_LISTA_FONDOS = "/html/body/div[1]/footer/div[2]/div/div[1]/div/ul"
XPATH_LISTA_DOCUMENTOS = "/html/body/div[1]/div/main/section[3]/div[1]/div[2]/ul"

# Texto del enlace (normalizado) -> sufijo del fichero descargado
DOCUMENTOS_OBJETIVO = {
    "datos fundamentales": "datos_fundamentales",
    "ficha del fondo": "ficha_fondo",
}

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
    return ejecutar_ingesta(args, ScraperBestinver, "bestinver", BASE_URL)

if __name__ == "__main__":
    sys.exit(main())
