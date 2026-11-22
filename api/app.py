"""Factoría y punto de entrada ASGI de la API de fondos."""

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError

from api.dependencies import validar_correlation_id
from api.http.errors import (
    manejar_error_repositorio,
    manejar_error_validacion,
    manejar_fondo_no_encontrado,
)
from api.http.middleware import CorrelationIdMiddleware
from api.repositories.base import ErrorRepositorio
from api.repositories.memory import RepositorioFondosEnMemoria
from api.routes import router_fondos, router_gestoras, router_kids, router_system
from api.services.errors import FondoNoEncontrado
from api.services.fondos import ServicioFondos


def crear_aplicacion(servicio: ServicioFondos | None = None) -> FastAPI:
    """Crea una aplicación con el servicio indicado o con datos semilla."""

    app = FastAPI(
        title="API de fondos de inversión",
        version="0.1.0",
        description="Consulta de gestoras, fondos y versiones de documentos KID.",
        dependencies=[Depends(validar_correlation_id)],
    )
    app.state.servicio_fondos = (
        servicio
        if servicio is not None
        else ServicioFondos(RepositorioFondosEnMemoria.con_datos_semilla())
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.add_exception_handler(FondoNoEncontrado, manejar_fondo_no_encontrado)
    app.add_exception_handler(RequestValidationError, manejar_error_validacion)
    app.add_exception_handler(ErrorRepositorio, manejar_error_repositorio)

    app.include_router(router_system)
    app.include_router(router_gestoras)
    app.include_router(router_fondos)
    app.include_router(router_kids)
    return app


app = crear_aplicacion()
