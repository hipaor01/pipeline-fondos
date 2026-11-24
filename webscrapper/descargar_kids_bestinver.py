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

import requests

if __package__:
    from .base import Documento, Incidencia, ResultadoIngesta
    from .ingesta import ejecutar as ejecutar_ingesta
    from .ingesta import (
        ejecutar_cli,
        informar,
        normalizar,
        obtener_arbol,
    )
else:
    from base import Documento, Incidencia, ResultadoIngesta
    from ingesta import ejecutar as ejecutar_ingesta
    from ingesta import (
        ejecutar_cli,
        informar,
        normalizar,
        obtener_arbol,
    )

BASE_URL = "https://www.bestinver.es/fondos-de-inversion/"

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
    def filtrar(enlaces):
        fondos, vistos = [], set()
        for a in enlaces:
            url = urljoin(BASE_URL, a.get("href"))
            nombre = " ".join(a.text_content().split())
            partes = [p for p in urlparse(url).path.split("/") if p]
            if len(partes) != 2 or partes[0] != "fondos-de-inversion":
                continue
            if url not in vistos:
                vistos.add(url)
                fondos.append((nombre, url))
        return fondos

    fondos = filtrar(arbol.xpath(f"{XPATH_LISTA_FONDOS}//a[@href]"))
    if not fondos:
        informar("[aviso] Listado principal sin fondos, usando respaldo.")
        fondos = filtrar(arbol.xpath("//footer//a[contains(@href, '/fondos-de-inversion/') ]"))
    return fondos

def obtener_documentos(session: requests.Session, url_fondo: str) -> tuple[dict[str, set[str]], list[tuple[str, str]]]:
    """Devuelve documentos y enlaces a productos de una posible categoría."""
    arbol = obtener_arbol(session, url_fondo)
    def filtrar(enlaces):
        encontrados = {}
        for a in enlaces:
            texto = normalizar(a.text_content())
            for objetivo, sufijo in DOCUMENTOS_OBJETIVO.items():
                if texto == objetivo:
                    encontrados.setdefault(sufijo, set()).add(urljoin(url_fondo, a.get("href")))
        return encontrados

    encontrados = filtrar(arbol.xpath(f"{XPATH_LISTA_DOCUMENTOS}//a[@href]"))
    if not all(tipo in encontrados for tipo in DOCUMENTOS_OBJETIVO.values()):
        informar("    [aviso] Faltan documentos en el bloque principal, usando respaldo.")
        respaldo = filtrar(arbol.xpath("//main//a[contains(@href, '.pdf')]"))
        for tipo, urls in respaldo.items():
            if tipo not in encontrados:
                encontrados[tipo] = urls
    hijos = {}
    if not encontrados:
        origen = urlparse(url_fondo)
        prefijo = origen.path.rstrip("/") + "/"
        for enlace in arbol.xpath("//main//a[@href]"):
            destino = urlparse(urljoin(url_fondo, enlace.get("href")))
            resto = destino.path.removeprefix(prefijo).strip("/")
            if (destino.scheme != "https" or destino.hostname != origen.hostname
                    or not destino.path.startswith(prefijo) or not resto or "/" in resto
                    or resto.lower().endswith(".pdf")):
                continue
            url = f"https://{destino.netloc}{prefijo}{resto}/"
            nombre = " ".join(enlace.text_content().split())
            hijos.setdefault(url, nombre if nombre and normalizar(nombre) != "ver producto" else resto)
    return encontrados, [(nombre, url) for url, nombre in hijos.items()]

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
        vistos = {url for _, url in fondos}
        for nombre, url in fondos:
            slug = [p for p in urlparse(url).path.split("/") if p][-1]
            informar(f"- {nombre} ({url})")
            time.sleep(self.delay)
            try:
                encontrados, hijos = obtener_documentos(self.session, url)
            except requests.RequestException as error:
                informar(f"    [error] no se pudo abrir la página: {error}")
                self.fallos.append(Incidencia("pagina", str(error), fondo=nombre, url=url))
                continue
            if hijos:
                for hijo_nombre, hijo_url in hijos:
                    if hijo_url not in vistos:
                        vistos.add(hijo_url)
                        fondos.append((hijo_nombre, hijo_url))
                continue
            for sufijo, tipo in (("datos_fundamentales", "kid"), ("ficha_fondo", "ficha_fondo")):
                if sufijo not in encontrados:
                    informar(f"    [sin documento] {sufijo}")
                    self.ausentes.append(Incidencia("ausente", "Documento no encontrado", nombre, tipo, url))
                    if tipo == "kid":
                        self.fallos.append(Incidencia("kid_ausente", "KID no encontrado", nombre, tipo, url))
                    continue
                urls = encontrados[sufijo]
                if len(urls) > 1:
                    self.fallos.append(Incidencia("documentos_ambiguos", "Varios enlaces distintos para el mismo tipo", nombre, tipo, url))
                    informar(f"    [error] varios enlaces para {tipo}")
                    continue
                documentos.append(Documento("bestinver", slug, tipo, next(iter(urls)), nombre))
        if fondos and not any(documento.tipo == "kid" for documento in documentos):
            self.fallos.append(Incidencia("listado", "No se encontraron documentos KID", url=BASE_URL))
        return documentos

def main() -> int:
    return ejecutar_cli(ScraperBestinver, "bestinver", BASE_URL, __doc__)

def ejecutar(args: argparse.Namespace) -> ResultadoIngesta:
    return ejecutar_ingesta(args, ScraperBestinver, "bestinver", BASE_URL)

if __name__ == "__main__":
    sys.exit(main())
