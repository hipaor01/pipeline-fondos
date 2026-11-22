"""Middleware HTTP compartido por todos los endpoints."""

from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from api.models.common import TAMANO_CORRELATION_ID_MAXIMO


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Asigna y devuelve un identificador de correlación por petición."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        recibido = request.headers.get("X-Correlation-Id")
        correlation_id = (
            recibido
            if recibido and len(recibido) <= TAMANO_CORRELATION_ID_MAXIMO
            else str(uuid4())
        )
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Correlation-Id"] = correlation_id
        return response
