"""Tipos y modelos compartidos por las respuestas de la API."""

from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

PAGINA_INICIAL = 1
TAMANO_PAGINA_POR_DEFECTO = 20
TAMANO_PAGINA_MINIMO = 1
TAMANO_PAGINA_MAXIMO = 100
TAMANO_CORRELATION_ID_MAXIMO = 128


Isin = Annotated[
    str,
    StringConstraints(
        pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$",
    ),
]
"""Código ISIN de doce caracteres que identifica una clase de fondo."""


CodigoGestora = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
"""Identificador legible y estable de una gestora."""


CorrelationId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=TAMANO_CORRELATION_ID_MAXIMO),
]
"""Identificador utilizado para correlacionar una petición y sus logs."""


class ModeloAPI(BaseModel):
    """Configuración común para los modelos expuestos por la API."""

    model_config = ConfigDict(extra="forbid")


class Paginacion(ModeloAPI):
    """Metadatos de una respuesta paginada."""

    pagina: Annotated[int, Field(ge=PAGINA_INICIAL)]
    tamano_pagina: Annotated[
        int,
        Field(ge=TAMANO_PAGINA_MINIMO, le=TAMANO_PAGINA_MAXIMO),
    ]
    total: Annotated[int, Field(ge=0)]


ElementoT = TypeVar("ElementoT")


class RespuestaPaginada(ModeloAPI, Generic[ElementoT]):
    """Colección tipada acompañada de sus metadatos de paginación."""

    datos: list[ElementoT]
    paginacion: Paginacion
