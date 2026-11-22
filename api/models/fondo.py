"""Modelos públicos de los fondos y sus clases."""

from datetime import date
from typing import Annotated

from pydantic import Field, StringConstraints

from api.models.common import Isin, ModeloAPI, RespuestaPaginada
from api.models.gestora import Gestora

NombreProducto = Annotated[
    str,
    StringConstraints(min_length=1, max_length=300),
]
"""Nombre del fondo tal y como aparece en el KID."""


NombreClase = Annotated[
    str,
    StringConstraints(max_length=200),
]
"""Nombre opcional de la clase o serie del fondo."""


IndicadorRiesgo = Annotated[int, Field(ge=1, le=7)]
"""Indicador resumido de riesgo (SRI), comprendido entre 1 y 7."""


ValorNoNegativo = Annotated[float, Field(ge=0, allow_inf_nan=False)]
"""Valor decimal finito que no puede ser negativo."""


class FondoBase(ModeloAPI):
    """Información común de una clase de fondo identificada por su ISIN."""

    isin: Isin
    nombre_producto: NombreProducto
    nombre_clase: NombreClase | None
    gestora: Gestora
    fecha_ultimo_kid: date | None
    sri: IndicadorRiesgo | None


class FondoResumen(FondoBase):
    """Representación de un fondo dentro de un listado."""


class FondoDetalle(FondoBase):
    """Detalle de un fondo con los datos de su KID más reciente."""

    periodo_mantenimiento_anios: ValorNoNegativo | None
    gastos_corrientes_pct: ValorNoNegativo | None
    costes_entrada_pct: ValorNoNegativo | None
    costes_salida_pct: ValorNoNegativo | None


class RespuestaFondos(RespuestaPaginada[FondoResumen]):
    """Página de fondos."""
