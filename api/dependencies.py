"""Dependencias reutilizables por las rutas FastAPI."""

from datetime import date
from typing import Annotated

from fastapi import Depends, Header, Query, Request

from api.models.common import (
    PAGINA_INICIAL,
    TAMANO_PAGINA_MAXIMO,
    TAMANO_PAGINA_MINIMO,
    TAMANO_PAGINA_POR_DEFECTO,
    CodigoGestora,
    CorrelationId,
    Isin,
)
from api.repositories.base import ConsultaPaginada, FiltrosFondos, FiltrosKids
from api.services.fondos import ServicioFondos


def obtener_servicio_fondos(request: Request) -> ServicioFondos:
    """Obtiene el servicio configurado al crear la aplicación."""

    return request.app.state.servicio_fondos


def crear_consulta_paginada(
    pagina: Annotated[int, Query(ge=PAGINA_INICIAL)] = PAGINA_INICIAL,
    tamano_pagina: Annotated[
        int,
        Query(ge=TAMANO_PAGINA_MINIMO, le=TAMANO_PAGINA_MAXIMO),
    ] = TAMANO_PAGINA_POR_DEFECTO,
) -> ConsultaPaginada:
    """Convierte los parámetros HTTP en una consulta paginada."""

    return ConsultaPaginada(pagina=pagina, tamano_pagina=tamano_pagina)


def crear_filtros_fondos(
    gestora: Annotated[CodigoGestora | None, Query()] = None,
    isin: Annotated[Isin | None, Query()] = None,
    nombre: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
) -> FiltrosFondos:
    """Convierte los parámetros HTTP en filtros de fondos."""

    return FiltrosFondos(gestora=gestora, isin=isin, nombre=nombre)


def crear_filtros_kids(
    gestora: Annotated[CodigoGestora | None, Query()] = None,
    isin: Annotated[Isin | None, Query()] = None,
    fecha: Annotated[date | None, Query()] = None,
) -> FiltrosKids:
    """Convierte los parámetros HTTP en filtros de versiones KID."""

    return FiltrosKids(gestora=gestora, isin=isin, fecha_documento=fecha)


def validar_correlation_id(
    x_correlation_id: Annotated[
        CorrelationId | None,
        Header(alias="X-Correlation-Id"),
    ] = None,
) -> None:
    """Valida la cabecera aunque su gestión corresponda al middleware."""


ServicioFondosDependencia = Annotated[ServicioFondos, Depends(obtener_servicio_fondos)]
ConsultaPaginadaDependencia = Annotated[
    ConsultaPaginada,
    Depends(crear_consulta_paginada),
]
FiltrosFondosDependencia = Annotated[FiltrosFondos, Depends(crear_filtros_fondos)]
FiltrosKidsDependencia = Annotated[FiltrosKids, Depends(crear_filtros_kids)]
