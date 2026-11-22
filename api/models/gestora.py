"""Modelos públicos de las sociedades gestoras."""

from typing import Annotated

from pydantic import StringConstraints

from api.models.common import CodigoGestora, ModeloAPI, RespuestaPaginada

NombreGestora = Annotated[
    str,
    StringConstraints(min_length=1, max_length=200),
]
"""Nombre visible de una sociedad gestora."""


class Gestora(ModeloAPI):
    """Sociedad gestora disponible para consulta."""

    codigo: CodigoGestora
    nombre: NombreGestora


class RespuestaGestoras(RespuestaPaginada[Gestora]):
    """Página de sociedades gestoras."""
