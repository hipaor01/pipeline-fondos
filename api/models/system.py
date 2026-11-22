"""Modelos de diagnóstico del servicio HTTP."""

from enum import Enum

from api.models.common import ModeloAPI


class EstadoSalud(str, Enum):
    """Estados posibles publicados por el endpoint de salud."""

    OK = "ok"


class EstadoServicio(ModeloAPI):
    """Estado y versión de la API desplegada."""

    estado: EstadoSalud
    servicio: str
    version: str
