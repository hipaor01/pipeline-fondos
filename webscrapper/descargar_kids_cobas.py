"""Descubre los KID y fichas por clase de Cobas AM y los guarda en S3."""

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

BASE_URL = "https://www.cobasam.com/productos/"
XPATH_LISTADO = (
    '//div[contains(concat(" ",normalize-space(@class)," ")," list-item ")]//a[@href]'
)
XPATH_CLASES = (
    '//section[contains(concat(" ",normalize-space(@class)," ")," with-docs ")]'
)
XPATH_RESPALDO = '//article[contains(concat(" ",normalize-space(@class)," ")," ficha ") and .//article[contains(concat(" ",normalize-space(@class)," ")," download-docs ")]]'
TIPOS = {"priip pdf": "kid", "ficha del fondo pdf": "ficha_fondo"}
PATRON_ISIN = r"(?<![A-Z0-9])[A-Z]{2}[A-Z0-9]{9}[0-9](?![A-Z0-9])"


def obtener_fondos(session: requests.Session) -> list[tuple[str, str]]:
    arbol = obtener_arbol(session, BASE_URL)

    def filtrar(enlaces):
        fondos = {}
        for enlace in enlaces:
            url = urljoin(BASE_URL, enlace.get("href"))
            partes = urlparse(url)
            segmentos = [parte for parte in partes.path.split("/") if parte]
            if (
                partes.scheme != "https"
                or partes.hostname != "www.cobasam.com"
                or len(segmentos) != 3
                or segmentos[:2] != ["productos", "inversion-libre"]
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
            cabeceras = enlace.xpath(
                'ancestor::div[contains(concat(" ",normalize-space(@class)," ")," list-item ")][1]//h3'
            )
            nombre = (
                " ".join(cabeceras[0].text_content().split())
                if cabeceras
                else segmentos[-1]
            )
            fondos.setdefault(url, nombre)
        return [(nombre, url) for url, nombre in fondos.items()]

    fondos = filtrar(arbol.xpath(XPATH_LISTADO))
    if not fondos:
        informar("[aviso] Listado principal no encontrado, usando respaldo.")
        fondos = filtrar(arbol.xpath("//a[@href]"))
    return fondos


class ScraperCobas:
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
        informar(f"Encontrados {len(fondos)} productos de Cobas.")
        documentos = []
        for nombre, url in fondos:
            slug = urlparse(url).path.strip("/").split("/")[-1].replace("_", "-")
            informar(f"- {nombre} ({url})")
            time.sleep(self.delay)
            try:
                arbol = obtener_arbol(self.session, url)
            except requests.RequestException as error:
                self.fallos.append(
                    Incidencia("pagina", str(error), fondo=nombre, url=url)
                )
                informar(f"    [error] no se pudo abrir la página: {error}")
                continue
            secciones = arbol.xpath(XPATH_CLASES)
            if not secciones:
                informar(
                    "    [aviso] Bloques de clase no encontrados, usando respaldo."
                )
                secciones = arbol.xpath(XPATH_RESPALDO)
            if not secciones:
                self.fallos.append(
                    Incidencia(
                        "clases",
                        "No se encontraron bloques de documentación",
                        nombre,
                        url=url,
                    )
                )
                continue
            for seccion in secciones:
                titulos = [
                    " ".join(h.text_content().split())
                    for h in seccion.xpath(".//h2|.//h3|.//h4")
                ]
                clases = {
                    m.group(1).upper()
                    for titulo in titulos
                    if (m := re.search(r"\bclase\s+([A-Z])\b", titulo, re.I))
                }
                codigos = set(re.findall(PATRON_ISIN, " ".join(seccion.itertext())))
                if (
                    len(clases) > 1
                    or len(codigos) > 1
                    or (len(secciones) > 1 and (not clases or not codigos))
                ):
                    self.fallos.append(
                        Incidencia(
                            "clase_ambigua",
                            "No se pudo identificar de forma única la clase y su ISIN",
                            nombre,
                            url=url,
                            nombre_clase=f"Clase {next(iter(clases))}" if len(clases) == 1 else None,
                            isin=next(iter(codigos)) if len(codigos) == 1 else None,
                        )
                    )
                    continue
                clase = next(iter(clases), None)
                isin = next(iter(codigos), None)
                slug_clase = f"{slug}-clase-{clase.lower()}" if clase else slug
                enlaces: dict[str, set[str]] = {}
                for enlace in seccion.xpath(".//a[@href]"):
                    tipo = TIPOS.get(normalizar(enlace.text_content()))
                    enlace_url = urljoin(url, enlace.get("href"))
                    partes = urlparse(enlace_url)
                    if (
                        tipo
                        and partes.scheme == "https"
                        and partes.path.lower().endswith(".pdf")
                    ):
                        enlaces.setdefault(tipo, set()).add(enlace_url)
                for tipo in ("kid", "ficha_fondo"):
                    urls = enlaces.get(tipo, set())
                    nombre_clase = f"Clase {clase}" if clase else None
                    if not urls:
                        self.ausentes.append(
                            Incidencia(
                                "ausente", "Documento no encontrado", nombre, tipo, url,
                                nombre_clase=nombre_clase, isin=isin,
                            )
                        )
                        if tipo == "kid":
                            self.fallos.append(
                                Incidencia(
                                    "kid_ausente",
                                    f"KID no encontrado para {nombre_clase or nombre}",
                                    nombre,
                                    tipo,
                                    url,
                                    nombre_clase=nombre_clase, isin=isin,
                                )
                            )
                    elif len(urls) > 1:
                        self.fallos.append(
                            Incidencia(
                                "documentos_ambiguos",
                                f"Varios enlaces para {nombre_clase or nombre}",
                                nombre,
                                tipo,
                                url,
                                nombre_clase=nombre_clase, isin=isin,
                            )
                        )
                    else:
                        documentos.append(
                            Documento(
                                "cobas",
                                slug_clase,
                                tipo,
                                next(iter(urls)),
                                nombre,
                                nombre_clase,
                                isin,
                            )
                        )
        if fondos and not any(d.tipo == "kid" for d in documentos):
            self.fallos.append(
                Incidencia("listado", "No se encontraron documentos KID", url=BASE_URL)
            )
        return documentos


def main() -> int:
    return ejecutar_cli(ScraperCobas, "cobas", BASE_URL, __doc__)


if __name__ == "__main__":
    sys.exit(main())
