"""Factoría y punto de entrada ASGI de la API de fondos."""

import os
from collections.abc import Mapping

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError

from api.dependencies import validar_correlation_id
from api.http.errors import (
    manejar_error_repositorio,
    manejar_error_validacion,
    manejar_fondo_no_encontrado,
)
from api.http.middleware import CorrelationIdMiddleware
from api.repositories.aurora import RepositorioFondosAurora
from api.repositories.base import ErrorRepositorio, RepositorioFondos
from api.repositories.memory import RepositorioFondosEnMemoria
from api.routes import router_fondos, router_gestoras, router_kids, router_system
from api.services.errors import FondoNoEncontrado
from api.services.fondos import ServicioFondos
from database.ejecutor import EjecutorDataAPI


class ErrorConfiguracionRepositorio(RuntimeError):
    """La fuente de datos seleccionada no está configurada correctamente."""


def crear_repositorio_desde_entorno(
    entorno: Mapping[str, str] | None = None,
) -> RepositorioFondos:
    """Construye el repositorio seleccionado mediante variables de entorno."""

    variables = os.environ if entorno is None else entorno
    tipo = variables.get("REPOSITORIO_FONDOS", "memoria").strip().lower()
    if tipo == "memoria":
        return RepositorioFondosEnMemoria.con_datos_semilla()
    if tipo != "aurora":
        raise ErrorConfiguracionRepositorio(
            "REPOSITORIO_FONDOS debe ser 'memoria' o 'aurora'."
        )

    nombres_variables = ("DB_CLUSTER_ARN", "DB_SECRET_ARN", "DB_NAME")
    configuracion = {
        nombre: variables.get(nombre, "").strip() for nombre in nombres_variables
    }
    faltantes = [nombre for nombre, valor in configuracion.items() if not valor]
    if faltantes:
        raise ErrorConfiguracionRepositorio(
            "Faltan variables para configurar Aurora: " + ", ".join(faltantes) + "."
        )

    ejecutor = EjecutorDataAPI(
        cluster_arn=configuracion["DB_CLUSTER_ARN"],
        secret_arn=configuracion["DB_SECRET_ARN"],
        base_datos=configuracion["DB_NAME"],
    )
    return RepositorioFondosAurora(ejecutor)


def crear_aplicacion(
    servicio: ServicioFondos | None = None,
    *,
    entorno: Mapping[str, str] | None = None,
) -> FastAPI:
    """Crea la aplicación con el servicio inyectado o configurado por entorno."""

    app = FastAPI(
        title="API de fondos de inversión",
        version="0.1.0",
        description="Consulta de gestoras, fondos y versiones de documentos KID.",
        dependencies=[Depends(validar_correlation_id)],
    )
    app.state.servicio_fondos = (
        servicio
        if servicio is not None
        else ServicioFondos(crear_repositorio_desde_entorno(entorno))
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
