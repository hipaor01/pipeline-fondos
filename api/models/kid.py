"""Modelos públicos de las versiones de documentos KID."""

from datetime import date
from typing import Annotated

from pydantic import StringConstraints

from api.models.common import Isin, ModeloAPI, RespuestaPaginada
from api.models.fondo import (
    IndicadorRiesgo,
    NombreClase,
    NombreProducto,
    ValorNoNegativo,
)
from api.models.gestora import Gestora

DocumentoSha256 = Annotated[
    str,
    StringConstraints(pattern=r"^[a-f0-9]{64}$"),
]
"""Huella SHA-256, en hexadecimal minúsculo, del PDF de origen."""


class KidVersion(ModeloAPI):
    """Datos extraídos de una versión válida de un documento KID."""

    isin: Isin
    nombre_producto: NombreProducto
    nombre_clase: NombreClase | None
    gestora: Gestora
    fecha_documento: date | None
    sri: IndicadorRiesgo
    periodo_mantenimiento_anios: ValorNoNegativo | None
    gastos_corrientes_pct: ValorNoNegativo | None
    costes_entrada_pct: ValorNoNegativo | None
    costes_salida_pct: ValorNoNegativo | None
    documento_sha256: DocumentoSha256


class RespuestaKids(RespuestaPaginada[KidVersion]):
    """Página de versiones de documentos KID."""
