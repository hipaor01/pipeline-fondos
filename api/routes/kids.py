"""Endpoints de consulta de documentos KID."""

from fastapi import APIRouter

from api.dependencies import (
    ConsultaPaginadaDependencia,
    FiltrosKidsDependencia,
    ServicioFondosDependencia,
)
from api.models.kid import RespuestaKids
from api.routes.common import RESPUESTAS_COMUNES

router = APIRouter(prefix="/kids", tags=["KID"])


@router.get(
    "",
    response_model=RespuestaKids,
    operation_id="listarKids",
    summary="Listar versiones de KID",
    responses=RESPUESTAS_COMUNES,
)
def listar_kids(
    servicio: ServicioFondosDependencia,
    filtros: FiltrosKidsDependencia,
    paginacion: ConsultaPaginadaDependencia,
) -> RespuestaKids:
    """Devuelve versiones KID filtradas y ordenadas."""

    return servicio.listar_kids(filtros, paginacion)
