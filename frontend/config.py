"""Configuración del frontend obtenida desde el entorno de ejecución."""

import os
from dataclasses import dataclass

API_BASE_URL_POR_DEFECTO = "http://localhost:8000"
API_TIMEOUT_SEGUNDOS_POR_DEFECTO = 5.0


@dataclass(frozen=True, slots=True)
class ConfiguracionFrontend:
    """Valores necesarios para comunicar Streamlit con la API."""

    api_base_url: str
    api_timeout_segundos: float

    @classmethod
    def desde_entorno(cls) -> "ConfiguracionFrontend":
        """Crea una configuración validada a partir de variables de entorno."""

        api_base_url = os.getenv("API_BASE_URL", API_BASE_URL_POR_DEFECTO).strip()
        if not api_base_url:
            raise ValueError("API_BASE_URL no puede estar vacía.")

        timeout_texto = os.getenv(
            "API_TIMEOUT_SECONDS",
            str(API_TIMEOUT_SEGUNDOS_POR_DEFECTO),
        )
        try:
            api_timeout_segundos = float(timeout_texto)
        except ValueError as error:
            raise ValueError("API_TIMEOUT_SECONDS debe ser un número.") from error

        if api_timeout_segundos <= 0:
            raise ValueError("API_TIMEOUT_SECONDS debe ser mayor que cero.")

        return cls(
            api_base_url=api_base_url.rstrip("/"),
            api_timeout_segundos=api_timeout_segundos,
        )
