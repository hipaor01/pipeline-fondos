"""Claves S3 de los contratos C1, C2 y C3 y conversión entre ellas.

C1 (P1 -> P2): raw/{gestora}/{AAAAMMDD}/{slug}_{tipo}.pdf
C2 (P2):       processed/markdown/{gestora}/{AAAAMMDD}/{nombre}.md
C3 (P2):       processed/structured/{gestora}/{AAAAMMDD}/{nombre}.json

`nombre` es siempre `{slug}_{tipo}`, de modo que las tres claves de un mismo
documento se derivan unas de otras sin consultar nada más.
"""

import re
from dataclasses import dataclass

PREFIJO_RAW = "raw/"
PREFIJO_MARKDOWN = "processed/markdown/"
PREFIJO_ESTRUCTURADO = "processed/structured/"

_SEGMENTO = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_PATRON_RELATIVO = re.compile(
    rf"^(?P<gestora>{_SEGMENTO})/(?P<fecha>\d{{8}})/(?P<nombre>[a-z0-9][a-z0-9_-]*)$"
)


class ClaveNoValida(ValueError):
    """La clave S3 no sigue el formato del contrato."""


@dataclass(frozen=True, slots=True)
class RutaDocumento:
    """Partes comunes a las claves de un documento en todas las etapas."""

    gestora: str
    fecha: str  # AAAAMMDD de descarga
    nombre: str  # {slug}_{tipo}

    @property
    def clave_raw(self) -> str:
        return f"{PREFIJO_RAW}{self._relativa}.pdf"

    @property
    def clave_markdown(self) -> str:
        return f"{PREFIJO_MARKDOWN}{self._relativa}.md"

    @property
    def clave_estructurada(self) -> str:
        return f"{PREFIJO_ESTRUCTURADO}{self._relativa}.json"

    @property
    def tipo_documento(self) -> str | None:
        """Tipo deducido del nombre si el metadato no viene (último `_tipo` conocido)."""
        for tipo in TIPOS_CONOCIDOS:
            if self.nombre.endswith(f"_{tipo}"):
                return tipo
        return None

    @property
    def _relativa(self) -> str:
        return f"{self.gestora}/{self.fecha}/{self.nombre}"


# Tipos que genera hoy el scraper de Bestinver; el metadato `tipo_documento`
# de C1 tiene prioridad sobre esta deducción.
TIPOS_CONOCIDOS = ("datos_fundamentales", "ficha_fondo")


def _parsear(clave: str, prefijo: str, extension: str) -> RutaDocumento:
    if not clave.startswith(prefijo) or not clave.endswith(extension):
        raise ClaveNoValida(
            f"'{clave}' no empieza por '{prefijo}' o no acaba en '{extension}'"
        )
    relativa = clave[len(prefijo) : -len(extension)]
    coincidencia = _PATRON_RELATIVO.match(relativa)
    if not coincidencia:
        raise ClaveNoValida(
            f"'{clave}' no sigue el formato {prefijo}{{gestora}}/{{AAAAMMDD}}/{{nombre}}{extension}"
        )
    return RutaDocumento(**coincidencia.groupdict())


def desde_clave_raw(clave: str) -> RutaDocumento:
    return _parsear(clave, PREFIJO_RAW, ".pdf")


def desde_clave_markdown(clave: str) -> RutaDocumento:
    return _parsear(clave, PREFIJO_MARKDOWN, ".md")
