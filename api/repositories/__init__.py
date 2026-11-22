"""Interfaces y tipos para acceder a los datos consultados por la API."""

from api.repositories.base import (
    ConsultaPaginada,
    ErrorRepositorio,
    FiltrosFondos,
    FiltrosKids,
    RepositorioFondos,
    ResultadoPaginado,
)
from api.repositories.memory import RepositorioFondosEnMemoria

__all__ = [
    "ConsultaPaginada",
    "ErrorRepositorio",
    "FiltrosFondos",
    "FiltrosKids",
    "RepositorioFondos",
    "RepositorioFondosEnMemoria",
    "ResultadoPaginado",
]
