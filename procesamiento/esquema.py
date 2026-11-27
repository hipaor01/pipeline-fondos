"""Esquema de extracción del KID (Anexo A) y documento de auditoría (contrato C3).

Hay dos representaciones a propósito:

1. `ESQUEMA_BEDROCK`: JSON Schema que se envía a Bedrock en
   `outputConfig.textFormat`. Bedrock solo admite un subconjunto de JSON Schema
   (sin `minimum`/`maximum`/`minLength`, `additionalProperties: false` obligatorio,
   máximo 16 propiedades anulables y 12 opcionales). Por eso todos los campos son
   obligatorios, los valores son anulables y las evidencias son texto ("" si no hay).
2. `DatosKID`: modelo Pydantic que valida lo que devuelve el modelo con las reglas
   que Bedrock no puede imponer (rangos, dígito de control del ISIN).

`ResultadoExtraccion` es el JSON de auditoría que se guarda SIEMPRE en
`processed/structured/...json`; `contracts/schemas/kid.schema.json` se genera a
partir de él (ver `python -m procesamiento.esquema`).
"""

import json
import sys
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

VERSION_ESQUEMA = "1.0.0"

# (campo, tipo JSON, descripción para el modelo). El orden se respeta en el esquema.
CAMPOS_KID: tuple[tuple[str, str, str], ...] = (
    (
        "isin",
        "string",
        "Código ISIN de la clase: 2 letras de país, 9 alfanuméricos y 1 dígito.",
    ),
    ("nombre_producto", "string", "Nombre del fondo tal y como aparece en el KID."),
    (
        "nombre_clase",
        "string",
        "Clase o serie (p. ej. «Clase C», «P Acc EUR»). Null si el KID no la indica.",
    ),
    (
        "gestora",
        "string",
        "Productor del PRIIP / sociedad gestora, tal y como aparece en el KID.",
    ),
    (
        "fecha_documento",
        "string",
        "Fecha de elaboración o validez del KID en formato AAAA-MM-DD.",
    ),
    (
        "sri",
        "integer",
        "Indicador resumido de riesgo (clase de riesgo), entero de 1 a 7.",
    ),
    (
        "periodo_mantenimiento_anios",
        "number",
        "Período de mantenimiento recomendado, en años.",
    ),
    (
        "gastos_corrientes_pct",
        "number",
        "Comisiones de gestión y otros costes administrativos o de funcionamiento, en % anual "
        "(1,8 % -> 1.8). No incluye costes de operación.",
    ),
    (
        "costes_entrada_pct",
        "number",
        "Costes de entrada en %. 0 si el KID dice que no se cobran.",
    ),
    (
        "costes_salida_pct",
        "number",
        "Costes de salida en %. 0 si el KID dice que no se cobran.",
    ),
)
NOMBRES_CAMPOS = tuple(nombre for nombre, _, _ in CAMPOS_KID)
CAMPOS_OBLIGATORIOS = ("isin", "nombre_producto", "gestora", "sri")

DESCRIPCION_EVIDENCIA = (
    "Fragmento LITERAL del documento del que sale '{campo}', copiado tal cual (mismas "
    "palabras, números y signos, sin traducir, resumir ni corregir y sin la marca Markdown). "
    "La frase o línea mínima que contiene el dato. Cadena vacía si '{campo}' es null."
)


def _construir_esquema_bedrock() -> dict[str, Any]:
    propiedades: dict[str, Any] = {}
    for nombre, tipo, descripcion in CAMPOS_KID:
        propiedad: dict[str, Any] = {"type": [tipo, "null"], "description": descripcion}
        if nombre == "isin":
            propiedad["pattern"] = r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$"
        if nombre == "fecha_documento":
            propiedad["pattern"] = r"^\d{4}-\d{2}-\d{2}$"
        propiedades[nombre] = propiedad
        propiedades[f"{nombre}_evidencia"] = {
            "type": "string",
            "description": DESCRIPCION_EVIDENCIA.format(campo=nombre),
        }
    return {
        "type": "object",
        "properties": propiedades,
        "required": list(propiedades),
        "additionalProperties": False,
    }


ESQUEMA_BEDROCK: dict[str, Any] = _construir_esquema_bedrock()


def isin_valido(isin: str) -> bool:
    """Comprueba el dígito de control del ISIN (algoritmo de Luhn sobre los dígitos expandidos)."""
    if len(isin) != 12 or not isin[:2].isalpha() or not isin[-1].isdigit():
        return False
    digitos = "".join(str(int(c, 36)) for c in isin[:-1])
    suma = 0
    for i, c in enumerate(reversed(digitos)):
        n = int(c)
        if i % 2 == 0:  # se duplican las posiciones impares contando desde la derecha
            n *= 2
            n = n - 9 if n > 9 else n
        suma += n
    return (10 - suma % 10) % 10 == int(isin[-1])


Porcentaje = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class DatosKID(BaseModel):
    """Datos del Anexo A ya validados. Los rangos son los de la API (C4)."""

    model_config = ConfigDict(extra="forbid")

    isin: str | None = Field(None, pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
    nombre_producto: str | None = Field(None, min_length=1, max_length=300)
    nombre_clase: str | None = Field(None, max_length=200)
    gestora: str | None = Field(None, min_length=1, max_length=200)
    fecha_documento: date | None = None
    sri: int | None = Field(None, ge=1, le=7)
    periodo_mantenimiento_anios: float | None = Field(
        None, ge=0, le=100, allow_inf_nan=False
    )
    gastos_corrientes_pct: Porcentaje | None = None
    costes_entrada_pct: Porcentaje | None = None
    costes_salida_pct: Porcentaje | None = None

    @field_validator("isin")
    @classmethod
    def _comprobar_digito_control(cls, valor: str | None) -> str | None:
        if valor is not None and not isin_valido(valor):
            raise ValueError("el dígito de control del ISIN no es válido")
        return valor

    @field_validator("nombre_clase", "nombre_producto", "gestora", mode="before")
    @classmethod
    def _vacio_a_null(cls, valor: Any) -> Any:
        if isinstance(valor, str):
            valor = " ".join(valor.split())
            return valor or None
        return valor


class Estado(StrEnum):
    VALID = "VALID"  # cumple todas las reglas: se inserta en Aurora
    REJECTED = "REJECTED"  # semántico: no se reintenta, queda auditado
    ERROR = "ERROR"  # técnico: agotó los reintentos y va a la DLQ


class Validacion(BaseModel):
    regla: str
    campo: str | None = None
    resultado: str  # "ok" | "fallo" | "aviso"
    detalle: str | None = None


class Evidencia(BaseModel):
    texto: str
    encontrada: bool


class Origen(BaseModel):
    """Trazabilidad hasta el PDF original (C1) y su Markdown (C2)."""

    gestora: str
    tipo_documento: str | None
    url_origen: str | None
    fecha_descarga: str | None
    correlation_id: str
    pdf_bucket: str
    pdf_key: str
    pdf_version_id: str | None
    pdf_sha256: str
    markdown_bucket: str | None = None
    markdown_key: str | None = None
    markdown_version_id: str | None = None
    modo_ocr: str | None = None
    conversor: str | None = None


class InfoModelo(BaseModel):
    model_id: str
    region: str
    latencia_ms: float | None = None
    tokens_entrada: int | None = None
    tokens_salida: int | None = None
    stop_reason: str | None = None


class ResultadoExtraccion(BaseModel):
    """Documento de auditoría del contrato C3."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = VERSION_ESQUEMA
    estado: Estado
    motivo: Annotated[
        str | None, Field(description="Resumen legible de por qué no es VALID")
    ] = None
    duplicado: Annotated[
        bool, Field(description="El PDF (mismo sha256) ya estaba cargado")
    ] = False
    source: Origen
    modelo: InfoModelo | None = None
    datos: DatosKID | None = None
    datos_crudos: Annotated[
        dict[str, Any] | None,
        Field(
            description="Respuesta del modelo tal cual, útil si no pasa la validación"
        ),
    ] = None
    evidencias: dict[str, Evidencia] = Field(default_factory=dict)
    validaciones: list[Validacion] = Field(default_factory=list)
    errores: list[str] = Field(default_factory=list)
    iniciado_en: datetime
    finalizado_en: datetime


RUTA_CONTRATO = (
    Path(__file__).resolve().parent.parent / "contracts" / "schemas" / "kid.schema.json"
)


def esquema_contrato() -> dict[str, Any]:
    esquema = ResultadoExtraccion.model_json_schema()
    esquema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    esquema["$id"] = f"pipeline-fondos/kid/{VERSION_ESQUEMA}"
    esquema["x-bedrock-output-schema"] = ESQUEMA_BEDROCK
    return esquema


def texto_contrato() -> str:
    return json.dumps(esquema_contrato(), ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    # Regenera el contrato C3: python -m procesamiento.esquema
    RUTA_CONTRATO.write_text(texto_contrato(), encoding="utf-8")
    print(f"Escrito {RUTA_CONTRATO}", file=sys.stderr)
