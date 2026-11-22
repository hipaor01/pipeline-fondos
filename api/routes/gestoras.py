"""Endpoints de consulta de sociedades gestoras."""

from fastapi import APIRouter

from api.dependencies import ConsultaPaginadaDependencia, ServicioFondosDependencia
from api.models.gestora import RespuestaGestoras
from api.routes.common import RESPUESTAS_COMUNES

router = APIRouter(prefix="/gestoras", tags=["Gestoras"])


@router.get(
    "",
    response_model=RespuestaGestoras,
    operation_id="listarGestoras",
    summary="Listar gestoras",
    responses=RESPUESTAS_COMUNES,
)
def listar_gestoras(
    servicio: ServicioFondosDependencia,
    paginacion: ConsultaPaginadaDependencia,
) -> RespuestaGestoras:
    """Devuelve una página de gestoras con orden determinista."""

    return servicio.listar_gestoras(paginacion)
