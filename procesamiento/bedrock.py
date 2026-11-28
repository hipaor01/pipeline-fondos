"""Llamada a Amazon Bedrock (Converse API) con salida estructurada nativa.

Se usa `outputConfig.textFormat` con un JSON Schema: Bedrock restringe la
decodificación al esquema, así que la respuesta es JSON válido por construcción
(no se pide «devuelve JSON» en el prompt ni se parsea texto libre).
"""

import json
from dataclasses import dataclass
from typing import Any

from procesamiento.esquema import ESQUEMA_BEDROCK

INSTRUCCIONES = """Eres un analista que extrae datos de Documentos de Datos Fundamentales (KID/DFI) de fondos de inversión españoles.

Reglas:
- Extrae solo lo que aparece en el documento. Si un dato no aparece, devuelve null y su evidencia como cadena vacía. No lo deduzcas ni lo inventes.
- Cada evidencia es un fragmento copiado LITERALMENTE del documento (sin la marca Markdown ni los separadores de tabla '|'), lo más corto posible pero que contenga el dato.
- Porcentajes como número en puntos porcentuales con punto decimal: «1,8 %» -> 1.8. Si el KID dice que no se cobran costes de entrada o salida, el valor es 0.
- gastos_corrientes_pct son solo las «comisiones de gestión y otros costes administrativos o de funcionamiento», no los costes de operación ni la incidencia anual total.
- La fecha del documento en formato AAAA-MM-DD (31/12/2025 -> 2025-12-31).
- El SRI es la clase de riesgo en la escala del 1 al 7."""


class RespuestaIncompleta(RuntimeError):
    """El modelo se quedó sin tokens: error técnico (reintentable con más tokens)."""


@dataclass(frozen=True, slots=True)
class RespuestaModelo:
    datos: dict[str, Any]
    latencia_ms: float | None
    tokens_entrada: int | None
    tokens_salida: int | None
    stop_reason: str | None


class ExtractorBedrock:
    def __init__(
        self, model_id: str, region: str, max_tokens: int = 2000, cliente: Any = None
    ) -> None:
        if cliente is None:
            import boto3
            from botocore.config import Config

            # La primera llamada con un esquema nuevo compila la gramática (hasta ~90 s).
            cliente = boto3.client(
                "bedrock-runtime",
                region_name=region,
                config=Config(
                    read_timeout=150, retries={"max_attempts": 4, "mode": "adaptive"}
                ),
            )
        self._cliente = cliente
        self.model_id = model_id
        self.region = region
        self._max_tokens = max_tokens

    def peticion(self, markdown: str) -> dict[str, Any]:
        return {
            "modelId": self.model_id,
            "system": [{"text": INSTRUCCIONES}],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"text": "Extrae los datos de este KID convertido a Markdown:"},
                        {"text": markdown},
                    ],
                }
            ],
            "inferenceConfig": {"maxTokens": self._max_tokens},
            "outputConfig": {
                "textFormat": {
                    "type": "json_schema",
                    "structure": {
                        "jsonSchema": {
                            "name": "datos_kid",
                            "description": "Campos del Anexo A del KID con su evidencia literal",
                            "schema": json.dumps(ESQUEMA_BEDROCK, ensure_ascii=False),
                        }
                    },
                }
            },
        }

    def extraer(self, markdown: str) -> RespuestaModelo:
        respuesta = self._cliente.converse(**self.peticion(markdown))
        stop_reason = respuesta.get("stopReason")
        if stop_reason == "max_tokens":
            raise RespuestaIncompleta(
                f"Respuesta truncada con maxTokens={self._max_tokens}"
            )
        bloques = respuesta["output"]["message"]["content"]
        texto = "".join(b.get("text", "") for b in bloques)
        uso = respuesta.get("usage", {})
        return RespuestaModelo(
            datos=json.loads(texto),
            latencia_ms=respuesta.get("metrics", {}).get("latencyMs"),
            tokens_entrada=uso.get("inputTokens"),
            tokens_salida=uso.get("outputTokens"),
            stop_reason=stop_reason,
        )
