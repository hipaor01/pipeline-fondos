"""Descubre KID y fichas de fondos y SICAV de Azvalor y los guarda en S3."""

import re
import sys
import time
from urllib.parse import urljoin, urlparse, urlunparse

import requests

if __package__:
    from .base import Documento, Incidencia
    from .ingesta import ejecutar_cli, informar, normalizar, obtener_arbol
else:
    from base import Documento, Incidencia
    from ingesta import ejecutar_cli, informar, normalizar, obtener_arbol

BASE_URL = "https://www.azvalor.com/fondos-de-inversion/"
XPATH_LISTADO = "//header//nav//a[@href]"
XPATH_DOCUMENTOS = "/html/body/div/div[2]/div/div[1]/div[3]/div/div[3]//a[@href]"
TIPOS = {
    "folleto simplificado (dfp)": "kid",
    "documento de datos fundamentales": "kid",
    "ficha del producto": "ficha_fondo",
    "ficha de producto": "ficha_fondo",
    "ficha producto": "ficha_fondo",
}


def obtener_fondos(session: requests.Session) -> list[tuple[str, str]]:
    arbol = obtener_arbol(session, BASE_URL)

    def filtrar(enlaces):
        fondos = {}
        for enlace in enlaces:
            url = urljoin(BASE_URL, enlace.get("href"))
            partes = urlparse(url)
            segmentos = [segmento for segmento in partes.path.split("/") if segmento]
            if (
                partes.scheme != "https"
                or partes.hostname != "www.azvalor.com"
                or len(segmentos) != 2
                or segmentos[0] not in {"fondos-de-inversion", "sicavs"}
            ):
                continue
            url = urlunparse(
                (
                    partes.scheme,
                    partes.netloc,
                    partes.path.rstrip("/") + "/",
                    "",
                    "",
                    "",
                )
            )
            nombre = " ".join(enlace.text_content().split())
            if nombre:
                fondos.setdefault(url, nombre)
        return [(nombre, url) for url, nombre in fondos.items()]

    fondos = filtrar(arbol.xpath(XPATH_LISTADO))
    if not fondos:
        informar("[aviso] Listado principal no encontrado, usando respaldo.")
        fondos = filtrar(arbol.xpath("//a[@href]"))
    return fondos


def obtener_documentos(session: requests.Session, url_fondo: str):
    arbol = obtener_arbol(session, url_fondo)

    def filtrar(enlaces):
        documentos = {}
        for enlace in enlaces:
            tipo = TIPOS.get(normalizar(enlace.text_content()))
            url = urljoin(url_fondo, enlace.get("href"))
            parsed = urlparse(url)
            if (
                tipo
                and parsed.scheme == "https"
                and parsed.path.lower().endswith(".pdf")
            ):
                documentos.setdefault(tipo, set()).add(url)
        return documentos

    documentos = filtrar(arbol.xpath(XPATH_DOCUMENTOS))
    if "kid" not in documentos:
        informar("    [aviso] Lista de documentos no encontrada, usando respaldo.")
        respaldo = filtrar(arbol.xpath("//a[@href]"))
        for tipo, urls in respaldo.items():
            documentos.setdefault(tipo, set()).update(urls)
    codigos = set()
    for elemento in arbol.xpath('//div[span[normalize-space(.)="ISIN"]]'):
        codigos.update(
            re.findall(
                r"(?<![A-Z0-9])[A-Z]{2}[A-Z0-9]{9}[0-9](?![A-Z0-9])",
                " ".join(elemento.itertext()),
            )
        )
    return documentos, next(iter(codigos)) if len(codigos) == 1 else None


class ScraperAzvalor:
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
            self.fallos.append(
                Incidencia("listado", "No se encontraron fondos", url=BASE_URL)
            )
        informar(f"Encontrados {len(fondos)} productos de Azvalor.")
        documentos = []
        for nombre, url in fondos:
            slug = urlparse(url).path.strip("/").split("/")[-1]
            informar(f"- {nombre} ({url})")
            time.sleep(self.delay)
            try:
                encontrados, isin = obtener_documentos(self.session, url)
            except requests.RequestException as error:
                self.fallos.append(
                    Incidencia("pagina", str(error), fondo=nombre, url=url)
                )
                informar(f"    [error] no se pudo abrir la página: {error}")
                continue
            clase = re.search(r"-(?:clase|lux)-([ir])$", slug)
            for tipo in ("kid", "ficha_fondo"):
                urls = encontrados.get(tipo, set())
                if not urls:
                    self.ausentes.append(
                        Incidencia(
                            "ausente", "Documento no encontrado", nombre, tipo, url
                        )
                    )
                    informar(f"    [sin documento] {tipo}")
                elif len(urls) > 1:
                    self.fallos.append(
                        Incidencia(
                            "documentos_ambiguos",
                            "Varios enlaces distintos para el mismo tipo",
                            nombre,
                            tipo,
                            url,
                        )
                    )
                    informar(f"    [error] varios enlaces para {tipo}")
                else:
                    documentos.append(
                        Documento(
                            "azvalor",
                            slug,
                            tipo,
                            next(iter(urls)),
                            nombre,
                            f"Clase {clase.group(1).upper()}" if clase else None,
                            isin,
                        )
                    )
        if fondos and not any(d.tipo == "kid" for d in documentos):
            self.fallos.append(
                Incidencia("listado", "No se encontraron documentos KID", url=BASE_URL)
            )
        return documentos


def main() -> int:
    return ejecutar_cli(ScraperAzvalor, "azvalor", BASE_URL, __doc__)


if __name__ == "__main__":
    sys.exit(main())
