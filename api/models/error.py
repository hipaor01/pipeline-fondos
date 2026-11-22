"""Modelos públicos de las respuestas de error."""

from typing import Annotated

from pydantic import Field, StringConstraints

from api.models.common import CorrelationId, ModeloAPI

CodigoError = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Z][A-Z0-9_]*$"),
]
"""Código estable de error procesable por los clientes de la API."""


class DetalleError(ModeloAPI):
    """Error de validación asociado a un parámetro o campo concreto."""

    campo: str
    mensaje: str


class Error(ModeloAPI):
    """Respuesta homogénea para los errores de la API."""

    codigo: CodigoError
    mensaje: str
    correlation_id: CorrelationId
    detalles: list[DetalleError] = Field(default_factory=list)
