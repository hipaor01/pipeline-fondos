"""Reglas que deciden si una extracción es VALID o REJECTED (contrato C3).

Reglas que rechazan:
- La respuesta del modelo no pasa `DatosKID` (rango, ISIN con dígito de control mal...).
- Falta un campo obligatorio: isin, nombre_producto, gestora o sri.
- Un valor no nulo no tiene evidencia, o su evidencia no aparece en el Markdown.
- El ISIN no aparece dentro de su propia evidencia.

Reglas que solo avisan (quedan en el JSON pero no rechazan):
- Un número no aparece literalmente en su evidencia (p. ej. «No cobramos comisión
  de entrada» para un 0 %): es habitual y correcto.
"""

import re
from typing import Any

from pydantic import ValidationError

from procesamiento.esquema import (
    CAMPOS_OBLIGATORIOS,
    NOMBRES_CAMPOS,
    DatosKID,
    Estado,
    Evidencia,
    Validacion,
)


def normalizar(texto: str) -> str:
    """Quita marca Markdown/HTML y todos los espacios, y pasa a minúsculas.

    pymupdf4llm parte a veces palabras entre celdas de tabla («Período de ma|ntenimiento»),
    así que se comparan los textos sin espacios ni separadores.
    """
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = re.sub(r"[*_~`#|>]", "", texto)
    return re.sub(r"\s+", "", texto).lower()


def _variantes_numero(valor: float) -> set[str]:
    """Formas en que un número puede aparecer escrito: 1.8 -> {'1.8', '1,8', '1,80', ...}."""
    variantes = set()
    for decimales in range(0, 3):
        texto = f"{valor:.{decimales}f}"
        if float(texto) == valor:
            variantes.update({texto, texto.replace(".", ",")})
    return variantes


class ResultadoValidacion:
    def __init__(self) -> None:
        self.validaciones: list[Validacion] = []
        self.evidencias: dict[str, Evidencia] = {}
        self.datos: DatosKID | None = None

    @property
    def fallos(self) -> list[Validacion]:
        return [v for v in self.validaciones if v.resultado == "fallo"]

    @property
    def estado(self) -> Estado:
        return Estado.REJECTED if self.fallos or self.datos is None else Estado.VALID

    @property
    def motivo(self) -> str | None:
        if not self.fallos:
            return None
        return "; ".join(
            f"{v.regla}({v.campo})" if v.campo else v.regla for v in self.fallos
        )

    def anotar(
        self,
        regla: str,
        resultado: str,
        campo: str | None = None,
        detalle: str | None = None,
    ) -> None:
        self.validaciones.append(
            Validacion(regla=regla, campo=campo, resultado=resultado, detalle=detalle)
        )


def validar_extraccion(respuesta: dict[str, Any], markdown: str) -> ResultadoValidacion:
    """Aplica todas las reglas a la respuesta cruda del modelo."""
    r = ResultadoValidacion()
    texto_doc = normalizar(markdown)

    valores = {campo: respuesta.get(campo) for campo in NOMBRES_CAMPOS}
    try:
        r.datos = DatosKID.model_validate(valores)
        r.anotar("esquema", "ok")
    except ValidationError as error:
        for detalle in error.errors():
            campo = str(detalle["loc"][0]) if detalle["loc"] else None
            r.anotar("esquema", "fallo", campo, detalle["msg"])
        return r

    datos = r.datos.model_dump()
    for campo in CAMPOS_OBLIGATORIOS:
        if datos[campo] is None:
            r.anotar(
                "obligatorio",
                "fallo",
                campo,
                "el campo no se ha encontrado en el documento",
            )

    for campo in NOMBRES_CAMPOS:
        valor = datos[campo]
        evidencia = (respuesta.get(f"{campo}_evidencia") or "").strip()
        if valor is None:
            continue
        if not evidencia:
            r.anotar("evidencia", "fallo", campo, "valor sin evidencia")
            continue
        encontrada = normalizar(evidencia) in texto_doc
        r.evidencias[campo] = Evidencia(texto=evidencia, encontrada=encontrada)
        if not encontrada:
            r.anotar(
                "evidencia", "fallo", campo, "la evidencia no aparece en el documento"
            )
            continue
        _coherencia(r, campo, valor, evidencia)

    return r


def _coherencia(r: ResultadoValidacion, campo: str, valor: Any, evidencia: str) -> None:
    evidencia_norm = normalizar(evidencia)
    if campo == "isin":
        if valor.lower() not in evidencia_norm:
            r.anotar("coherencia", "fallo", campo, "el ISIN no aparece en su evidencia")
        return
    if campo == "sri":
        if str(valor) not in evidencia_norm:
            r.anotar(
                "coherencia",
                "aviso",
                campo,
                "el número de clase de riesgo no aparece en la evidencia",
            )
        return
    if isinstance(valor, float) and not any(
        v in evidencia_norm for v in _variantes_numero(valor)
    ):
        r.anotar(
            "coherencia", "aviso", campo, f"{valor} no aparece escrito en la evidencia"
        )
