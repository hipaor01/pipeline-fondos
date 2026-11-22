"""Endpoints de consulta de fondos."""

from typing import Annotated

from fastapi import APIRouter, Path

from api.dependencies import (
    ConsultaPaginadaDependencia,
    FiltrosFondosDependencia,
    ServicioFondosDependencia,
)
from api.models.common import Isin
from api.models.error import Error
from api.models.fondo import FondoDetalle, RespuestaFondos
from api.routes.common import RESPUESTAS_COMUNES

router = APIRouter(prefix="/fondos", tags=["Fondos"])


@router.get(
    "",
    response_model=RespuestaFondos,
    operation_id="listarFondos",
    summary="Listar fondos",
    responses=RESPUESTAS_COMUNES,
)
def listar_fondos(
    servicio: ServicioFondosDependencia,
    filtros: FiltrosFondosDependencia,
    paginacion: ConsultaPaginadaDependencia,
) -> RespuestaFondos:
    """Devuelve una página de fondos aplicando los filtros indicados."""

    return servicio.listar_fondos(filtros, paginacion)


@router.get(
    "/{isin}",
    response_model=FondoDetalle,
    operation_id="obtenerFondo",
    summary="Obtener el detalle de un fondo por ISIN",
    responses={
        **RESPUESTAS_COMUNES,
        404: {"model": Error, "description": "Fondo no encontrado"},
    },
)
def obtener_fondo(
    isin: Annotated[Isin, Path()],
    servicio: ServicioFondosDependencia,
) -> FondoDetalle:
    """Devuelve el fondo y los datos de su KID más reciente."""

    return servicio.obtener_fondo(isin)
