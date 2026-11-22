"""Contrato de descubrimiento de documentos de una gestora."""

from dataclasses import dataclass
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


class ScraperGestora(Protocol):
    """Descubre documentos; la descarga y el almacenamiento son independientes."""

    def descubrir(self) -> list[Documento]: ...
