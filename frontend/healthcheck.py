"""Comprobación local de salud del proceso Streamlit."""

import os
import sys
import urllib.request

RUTA_SALUD_STREAMLIT = "/_stcore/health"
PUERTO_STREAMLIT_POR_DEFECTO = 8501
TIMEOUT_SEGUNDOS = 3.0


def construir_url_salud() -> str:
    """Construye la URL local usando el mismo puerto que Streamlit."""

    puerto = int(
        os.getenv("STREAMLIT_SERVER_PORT", str(PUERTO_STREAMLIT_POR_DEFECTO))
    )
    if not 1 <= puerto <= 65535:
        raise ValueError("STREAMLIT_SERVER_PORT debe ser un puerto válido.")
    return f"http://127.0.0.1:{puerto}{RUTA_SALUD_STREAMLIT}"


def comprobar_salud(url: str) -> bool:
    """Devuelve si el endpoint de salud responde con HTTP 200."""

    with urllib.request.urlopen(url, timeout=TIMEOUT_SEGUNDOS) as respuesta:
        return respuesta.status == 200


def main() -> int:
    """Adapta la comprobación al código de salida esperado por Docker y ECS."""

    try:
        url = construir_url_salud()
        if comprobar_salud(url):
            return 0
        print(f"El endpoint de salud no está disponible: {url}", file=sys.stderr)
    except Exception as error:
        print(f"La comprobación de salud ha fallado: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
