"""Logs JSON con correlation_id y métricas en CloudWatch Embedded Metric Format.

EMF permite publicar métricas escribiendo una línea JSON en stdout: no hace
falta llamar a la API de CloudWatch ni dar permisos extra a la Lambda.
"""

import json
import sys
import time
from datetime import UTC, datetime
from typing import Any

ESPACIO_METRICAS = "PipelineFondos/Procesamiento"


def log(nivel: str, mensaje: str, **campos: Any) -> None:
    """Escribe una línea JSON; CloudWatch Logs Insights puede filtrar por cualquier campo."""
    registro = {
        "timestamp": datetime.now(UTC).isoformat(),
        "nivel": nivel,
        "mensaje": mensaje,
        **campos,
    }
    print(
        json.dumps(registro, ensure_ascii=False, default=str),
        file=sys.stdout,
        flush=True,
    )


def metrica_resultado(
    etapa: str,
    resultado: str,
    duracion_ms: float,
    correlation_id: str | None = None,
    **propiedades: Any,
) -> None:
    """Publica `Documentos` (contador) y `DuracionProceso` por etapa y resultado."""
    documento = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": ESPACIO_METRICAS,
                    "Dimensions": [["Etapa", "Resultado"], ["Etapa"]],
                    "Metrics": [
                        {"Name": "Documentos", "Unit": "Count"},
                        {"Name": "DuracionProceso", "Unit": "Milliseconds"},
                    ],
                }
            ],
        },
        "Etapa": etapa,
        "Resultado": resultado,
        "Documentos": 1,
        "DuracionProceso": round(duracion_ms, 1),
        "correlation_id": correlation_id,
        **propiedades,
    }
    print(
        json.dumps(documento, ensure_ascii=False, default=str),
        file=sys.stdout,
        flush=True,
    )


class Cronometro:
    """Mide milisegundos transcurridos desde su creación."""

    def __init__(self) -> None:
        self._inicio = time.perf_counter()
        self.inicio_utc = datetime.now(UTC)

    @property
    def ms(self) -> float:
        return (time.perf_counter() - self._inicio) * 1000
