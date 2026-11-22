"""Conversión de excepciones de aplicación en respuestas HTTP."""

import logging
from typing import cast

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.models.error import DetalleError, Error
from api.repositories.base import ErrorRepositorio
from api.services.errors import FondoNoEncontrado

logger = logging.getLogger(__name__)


def obtener_correlation_id(request: Request) -> str:
    """Devuelve el identificador asignado por el middleware a la petición."""

    return request.state.correlation_id


def crear_respuesta_error(
    request: Request,
    estado_http: int,
    codigo: str,
    mensaje: str,
    detalles: list[DetalleError] | None = None,
) -> JSONResponse:
    """Construye el formato de error común y conserva la trazabilidad."""

    correlation_id = obtener_correlation_id(request)
    error = Error(
        codigo=codigo,
        mensaje=mensaje,
        correlation_id=correlation_id,
        detalles=detalles or [],
    )
    return JSONResponse(
        status_code=estado_http,
        content=error.model_dump(mode="json"),
        headers={"X-Correlation-Id": correlation_id},
    )


async def manejar_fondo_no_encontrado(
    request: Request,
    excepcion: Exception,
) -> JSONResponse:
    """Traduce el error de negocio de fondo inexistente a HTTP 404."""

    error = cast(FondoNoEncontrado, excepcion)
    return crear_respuesta_error(
        request=request,
        estado_http=404,
        codigo=error.codigo,
        mensaje=str(error),
    )


async def manejar_error_validacion(
    request: Request,
    excepcion: Exception,
) -> JSONResponse:
    """Traduce los errores de parámetros al modelo público de error."""

    error = cast(RequestValidationError, excepcion)
    detalles = [
        DetalleError(
            campo=".".join(str(parte) for parte in detalle["loc"]),
            mensaje=detalle["msg"],
        )
        for detalle in error.errors()
    ]
    return crear_respuesta_error(
        request=request,
        estado_http=422,
        codigo="PARAMETRO_NO_VALIDO",
        mensaje="Uno o varios parámetros no son válidos.",
        detalles=detalles,
    )


async def manejar_error_repositorio(
    request: Request,
    excepcion: Exception,
) -> JSONResponse:
    """Oculta el detalle técnico y devuelve un error interno trazable."""

    error = cast(ErrorRepositorio, excepcion)
    logger.error(
        "Error al consultar el repositorio",
        extra={"correlation_id": obtener_correlation_id(request)},
        exc_info=(type(error), error, error.__traceback__),
    )
    return crear_respuesta_error(
        request=request,
        estado_http=500,
        codigo="ERROR_INTERNO",
        mensaje="No se ha podido completar la consulta.",
    )
