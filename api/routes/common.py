"""Metadatos OpenAPI compartidos entre las rutas."""

from typing import Any

from api.models.error import Error

RESPUESTAS_COMUNES: dict[int | str, dict[str, Any]] = {
    422: {"model": Error, "description": "Parámetros de petición no válidos"},
    429: {"model": Error, "description": "Límite de peticiones superado"},
    500: {"model": Error, "description": "Error técnico no esperado"},
}
