"""Endpoints de diagnóstico del servicio."""

from fastapi import APIRouter

from api.models.system import EstadoSalud, EstadoServicio
from api.routes.common import RESPUESTAS_COMUNES

router = APIRouter(tags=["Sistema"])


@router.get(
    "/health",
    response_model=EstadoServicio,
    operation_id="obtenerEstado",
    summary="Comprobar el estado de la API",
    responses={
        422: RESPUESTAS_COMUNES[422],
        500: RESPUESTAS_COMUNES[500],
    },
)
def obtener_estado() -> EstadoServicio:
    """Confirma que el proceso de la API está disponible."""

    return EstadoServicio(
        estado=EstadoSalud.OK,
        servicio="api-fondos",
        version="0.1.0",
    )
