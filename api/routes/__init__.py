"""Rutas HTTP de la API de fondos."""

from api.routes.fondos import router as router_fondos
from api.routes.gestoras import router as router_gestoras
from api.routes.kids import router as router_kids
from api.routes.system import router as router_system

__all__ = ["router_fondos", "router_gestoras", "router_kids", "router_system"]
