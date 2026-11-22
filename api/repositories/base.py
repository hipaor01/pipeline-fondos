"""Contrato de acceso a los datos de fondos, gestoras y documentos KID."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Generic, TypeVar

from api.models.common import (
    PAGINA_INICIAL,
    TAMANO_PAGINA_MAXIMO,
    TAMANO_PAGINA_MINIMO,
    TAMANO_PAGINA_POR_DEFECTO,
    CodigoGestora,
    Isin,
)
from api.models.fondo import FondoDetalle, FondoResumen
from api.models.gestora import Gestora
from api.models.kid import KidVersion


@dataclass(frozen=True, slots=True)
class ConsultaPaginada:
    """Posición y tamaño de una consulta paginada."""

    pagina: int = PAGINA_INICIAL
    tamano_pagina: int = TAMANO_PAGINA_POR_DEFECTO

    def __post_init__(self) -> None:
        if type(self.pagina) is not int or type(self.tamano_pagina) is not int:
            raise TypeError("La página y su tamaño deben ser números enteros.")
        if self.pagina < PAGINA_INICIAL:
            raise ValueError(f"La página debe ser mayor o igual que {PAGINA_INICIAL}.")
        if not TAMANO_PAGINA_MINIMO <= self.tamano_pagina <= TAMANO_PAGINA_MAXIMO:
            raise ValueError(
                "El tamaño de página debe estar entre "
                f"{TAMANO_PAGINA_MINIMO} y {TAMANO_PAGINA_MAXIMO}."
            )

    @property
    def desplazamiento(self) -> int:
        """Número de filas que debe omitir la consulta de datos."""

        return (self.pagina - PAGINA_INICIAL) * self.tamano_pagina


@dataclass(frozen=True, slots=True)
class FiltrosFondos:
    """Filtros opcionales del listado de fondos."""

    gestora: CodigoGestora | None = None
    isin: Isin | None = None
    nombre: str | None = None


@dataclass(frozen=True, slots=True)
class FiltrosKids:
    """Filtros opcionales del listado de versiones KID."""

    gestora: CodigoGestora | None = None
    isin: Isin | None = None
    fecha_documento: date | None = None


ElementoT = TypeVar("ElementoT")


@dataclass(frozen=True, slots=True)
class ResultadoPaginado(Generic[ElementoT]):
    """Elementos recuperados y total de filas que cumplen los filtros."""

    elementos: tuple[ElementoT, ...]
    total: int

    def __post_init__(self) -> None:
        if type(self.total) is not int:
            raise TypeError("El total debe ser un número entero.")
        if self.total < 0:
            raise ValueError("El total no puede ser negativo.")
        if self.total < len(self.elementos):
            raise ValueError("El total no puede ser menor que los elementos devueltos.")


class ErrorRepositorio(RuntimeError):
    """Error técnico producido al consultar la fuente de datos."""


class RepositorioFondos(ABC):
    """Interfaz de lectura que debe implementar cada fuente de datos."""

    @abstractmethod
    def listar_gestoras(
        self,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[Gestora]:
        """Devuelve las gestoras ordenadas por nombre y código."""

    @abstractmethod
    def listar_fondos(
        self,
        filtros: FiltrosFondos,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[FondoResumen]:
        """Devuelve los fondos ordenados por nombre de producto e ISIN."""

    @abstractmethod
    def obtener_fondo(self, isin: Isin) -> FondoDetalle | None:
        """Devuelve el fondo identificado por el ISIN o `None` si no existe."""

    @abstractmethod
    def listar_kids(
        self,
        filtros: FiltrosKids,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[KidVersion]:
        """Devuelve las versiones KID con el orden definido en OpenAPI."""
