"""Datos deterministas de demostración para el repositorio en memoria."""

from collections import defaultdict
from datetime import date

from api.models.fondo import FondoDetalle
from api.models.gestora import Gestora
from api.models.kid import KidVersion


def crear_datos_semilla() -> tuple[
    tuple[Gestora, ...],
    tuple[FondoDetalle, ...],
    tuple[KidVersion, ...],
]:
    """Crea gestoras, fondos y versiones KID coherentes entre sí."""

    gestoras = (
        Gestora(codigo="bestinver", nombre="Bestinver"),
        Gestora(codigo="azvalor", nombre="Azvalor Asset Management"),
        Gestora(codigo="cobas-am", nombre="Cobas Asset Management"),
    )
    gestoras_por_codigo = {gestora.codigo: gestora for gestora in gestoras}

    kids = (
        KidVersion(
            isin="ES0000000001",
            nombre_producto="Bestinfond",
            nombre_clase="Clase C",
            gestora=gestoras_por_codigo["bestinver"],
            fecha_documento=date(2026, 11, 19),
            sri=4,
            periodo_mantenimiento_anios=5,
            gastos_corrientes_pct=1.78,
            costes_entrada_pct=0,
            costes_salida_pct=0,
            documento_sha256="a" * 64,
        ),
        KidVersion(
            isin="ES0000000001",
            nombre_producto="Bestinfond",
            nombre_clase="Clase C",
            gestora=gestoras_por_codigo["bestinver"],
            fecha_documento=date(2025, 11, 19),
            sri=4,
            periodo_mantenimiento_anios=5,
            gastos_corrientes_pct=1.82,
            costes_entrada_pct=0,
            costes_salida_pct=0,
            documento_sha256="b" * 64,
        ),
        KidVersion(
            isin="ES0000000002",
            nombre_producto="Bestinver Internacional",
            nombre_clase=None,
            gestora=gestoras_por_codigo["bestinver"],
            fecha_documento=date(2026, 11, 18),
            sri=5,
            periodo_mantenimiento_anios=5,
            gastos_corrientes_pct=1.91,
            costes_entrada_pct=0,
            costes_salida_pct=0,
            documento_sha256="c" * 64,
        ),
        KidVersion(
            isin="ES0000000003",
            nombre_producto="Azvalor Internacional",
            nombre_clase="Clase A",
            gestora=gestoras_por_codigo["azvalor"],
            fecha_documento=date(2026, 11, 17),
            sri=5,
            periodo_mantenimiento_anios=5,
            gastos_corrientes_pct=2.04,
            costes_entrada_pct=0,
            costes_salida_pct=0,
            documento_sha256="d" * 64,
        ),
        KidVersion(
            isin="ES0000000004",
            nombre_producto="Cobas Internacional",
            nombre_clase="Clase C",
            gestora=gestoras_por_codigo["cobas-am"],
            fecha_documento=None,
            sri=5,
            periodo_mantenimiento_anios=5,
            gastos_corrientes_pct=1.85,
            costes_entrada_pct=0,
            costes_salida_pct=0,
            documento_sha256="e" * 64,
        ),
        KidVersion(
            isin="ES0000000005",
            nombre_producto="Cobas Selección",
            nombre_clase="Clase C",
            gestora=gestoras_por_codigo["cobas-am"],
            fecha_documento=date(2026, 11, 16),
            sri=4,
            periodo_mantenimiento_anios=5,
            gastos_corrientes_pct=1.79,
            costes_entrada_pct=0,
            costes_salida_pct=0,
            documento_sha256="f" * 64,
        ),
    )

    fondos = _crear_fondos_desde_kids(kids)
    return gestoras, fondos, kids


def _crear_fondos_desde_kids(kids: tuple[KidVersion, ...]) -> tuple[FondoDetalle, ...]:
    kids_por_isin: dict[str, list[KidVersion]] = defaultdict(list)
    for kid in kids:
        kids_por_isin[kid.isin].append(kid)

    fondos = []
    for isin, versiones in kids_por_isin.items():
        ultima_version = max(
            versiones,
            key=lambda kid: (
                kid.fecha_documento is not None,
                kid.fecha_documento or date.min,
                kid.documento_sha256,
            ),
        )
        fondos.append(
            FondoDetalle(
                isin=isin,
                nombre_producto=ultima_version.nombre_producto,
                nombre_clase=ultima_version.nombre_clase,
                gestora=ultima_version.gestora.model_copy(deep=True),
                fecha_ultimo_kid=ultima_version.fecha_documento,
                sri=ultima_version.sri,
                periodo_mantenimiento_anios=(
                    ultima_version.periodo_mantenimiento_anios
                ),
                gastos_corrientes_pct=ultima_version.gastos_corrientes_pct,
                costes_entrada_pct=ultima_version.costes_entrada_pct,
                costes_salida_pct=ultima_version.costes_salida_pct,
            )
        )

    return tuple(fondos)
