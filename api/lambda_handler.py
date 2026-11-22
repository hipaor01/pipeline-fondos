"""Punto de entrada de AWS Lambda para la aplicación FastAPI."""

from mangum import Mangum

from api.app import app

handler = Mangum(app, lifespan="off")
"""Adapta eventos de API Gateway HTTP API v2 al protocolo ASGI."""
