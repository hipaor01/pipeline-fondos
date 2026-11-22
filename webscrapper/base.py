"""Contrato de descubrimiento de documentos de una gestora."""

from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class Documento:
    """Referencia de origen a un documento de un fondo o clase."""

    gestora: str
    slug: str
    tipo: Literal["kid", "ficha_fondo"]
    url: str
    nombre_fondo: str
    nombre_clase: str | None = None
    isin: str | None = None


@dataclass(frozen=True, slots=True)
class Incidencia:
    etapa: str
    mensaje: str
    fondo: str | None = None
    tipo: str | None = None
    url: str | None = None
    clave: str | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class Subida:
    documento: Documento
    bucket: str
    clave: str
    version_id: str | None
    sha256: str
    fecha_descarga_utc: str


@dataclass(slots=True)
class ResultadoIngesta:
    subidos: list[Subida] = field(default_factory=list)
    ausentes: list[Incidencia] = field(default_factory=list)
    fallos: list[Incidencia] = field(default_factory=list)

    @property
    def estado(self) -> Literal["completa", "parcial", "fallida"]:
        if not self.subidos:
            return "fallida"
        return "parcial" if self.fallos else "completa"


class ScraperGestora(Protocol):
    """Descubre documentos; la descarga y el almacenamiento son independientes."""

    def descubrir(self) -> list[Documento]: ...
