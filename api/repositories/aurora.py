"""Repositorio de lectura de fondos sobre Aurora PostgreSQL."""

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from api.models.common import Isin
from api.models.fondo import FondoDetalle, FondoResumen
from api.models.gestora import Gestora
from api.models.kid import KidVersion
from api.repositories.base import (
    ConsultaPaginada,
    ErrorRepositorio,
    FiltrosFondos,
    FiltrosKids,
    RepositorioFondos,
    ResultadoPaginado,
)
from database.ejecutor import EjecutorSQL, Parametros

ModeloT = TypeVar("ModeloT", bound=BaseModel)
ResultadoT = TypeVar("ResultadoT")

COLUMNAS_FONDO_RESUMEN = """
    isin,
    nombre_producto,
    nombre_clase,
    gestora_codigo,
    gestora_nombre,
    fecha_ultimo_kid,
    sri
"""

COLUMNAS_FONDO_DETALLE = f"""
    {COLUMNAS_FONDO_RESUMEN},
    periodo_mantenimiento_anios,
    gastos_corrientes_pct,
    costes_entrada_pct,
    costes_salida_pct
"""

COLUMNAS_KID = """
    isin,
    nombre_producto,
    nombre_clase,
    gestora_codigo,
    gestora_nombre,
    fecha_documento,
    sri,
    periodo_mantenimiento_anios,
    gastos_corrientes_pct,
    costes_entrada_pct,
    costes_salida_pct,
    documento_sha256
"""


class RepositorioFondosAurora(RepositorioFondos):
    """Consulta las vistas públicas de la API mediante un ejecutor SQL."""

    def __init__(self, ejecutor: EjecutorSQL) -> None:
        self._sql = ejecutor

    def listar_gestoras(
        self,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[Gestora]:
        return self._proteger(
            lambda: self._listar_paginado(
                fuente="gestora",
                columnas="codigo, nombre",
                condiciones=(),
                parametros={},
                orden="lower(nombre), codigo",
                paginacion=paginacion,
                modelo=Gestora,
            )
        )

    def listar_fondos(
        self,
        filtros: FiltrosFondos,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[FondoResumen]:
        condiciones, parametros = self._crear_filtros_fondos(filtros)
        return self._proteger(
            lambda: self._listar_paginado(
                fuente="api_fondo",
                columnas=COLUMNAS_FONDO_RESUMEN,
                condiciones=condiciones,
                parametros=parametros,
                orden="lower(nombre_producto), isin",
                paginacion=paginacion,
                modelo=FondoResumen,
                anidar_gestora=True,
            )
        )

    def obtener_fondo(self, isin: Isin) -> FondoDetalle | None:
        def consultar() -> FondoDetalle | None:
            filas = self._sql.ejecutar(
                f"""
                SELECT {COLUMNAS_FONDO_DETALLE}
                FROM api_fondo
                WHERE isin = :isin
                LIMIT 1
                """,
                {"isin": isin},
            )
            if not filas:
                return None
            return FondoDetalle.model_validate(self._anidar_gestora(filas[0]))

        return self._proteger(consultar)

    def listar_kids(
        self,
        filtros: FiltrosKids,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[KidVersion]:
        condiciones, parametros = self._crear_filtros_kids(filtros)
        return self._proteger(
            lambda: self._listar_paginado(
                fuente="api_kid_version",
                columnas=COLUMNAS_KID,
                condiciones=condiciones,
                parametros=parametros,
                orden="fecha_documento DESC NULLS LAST, isin, documento_sha256",
                paginacion=paginacion,
                modelo=KidVersion,
                anidar_gestora=True,
            )
        )

    def _listar_paginado(
        self,
        *,
        fuente: str,
        columnas: str,
        condiciones: tuple[str, ...],
        parametros: Parametros,
        orden: str,
        paginacion: ConsultaPaginada,
        modelo: type[ModeloT],
        anidar_gestora: bool = False,
    ) -> ResultadoPaginado[ModeloT]:
        clausula_where = self._crear_clausula_where(condiciones)
        filas_total = self._sql.ejecutar(
            f"SELECT COUNT(*) AS total FROM {fuente}{clausula_where}",
            parametros,
        )
        if len(filas_total) != 1 or type(filas_total[0].get("total")) is not int:
            raise ValueError("La consulta de total no devolvió un entero.")

        parametros_pagina = {
            **parametros,
            "limite": paginacion.tamano_pagina,
            "desplazamiento": paginacion.desplazamiento,
        }
        filas = self._sql.ejecutar(
            f"""
            SELECT {columnas}
            FROM {fuente}{clausula_where}
            ORDER BY {orden}
            LIMIT :limite OFFSET :desplazamiento
            """,
            parametros_pagina,
        )
        elementos = tuple(
            modelo.model_validate(self._anidar_gestora(fila) if anidar_gestora else fila)
            for fila in filas
        )
        return ResultadoPaginado(
            elementos=elementos,
            total=filas_total[0]["total"],
        )

    @staticmethod
    def _crear_filtros_fondos(
        filtros: FiltrosFondos,
    ) -> tuple[tuple[str, ...], Parametros]:
        condiciones: list[str] = []
        parametros: Parametros = {}
        if filtros.gestora is not None:
            condiciones.append("gestora_codigo = :gestora")
            parametros["gestora"] = filtros.gestora
        if filtros.isin is not None:
            condiciones.append("isin = :isin")
            parametros["isin"] = filtros.isin
        if filtros.nombre is not None:
            condiciones.append(
                "strpos(lower(nombre_producto), lower(:nombre)) > 0"
            )
            parametros["nombre"] = filtros.nombre
        return tuple(condiciones), parametros

    @staticmethod
    def _crear_filtros_kids(
        filtros: FiltrosKids,
    ) -> tuple[tuple[str, ...], Parametros]:
        condiciones: list[str] = []
        parametros: Parametros = {}
        if filtros.gestora is not None:
            condiciones.append("gestora_codigo = :gestora")
            parametros["gestora"] = filtros.gestora
        if filtros.isin is not None:
            condiciones.append("isin = :isin")
            parametros["isin"] = filtros.isin
        if filtros.fecha_documento is not None:
            condiciones.append("fecha_documento = :fecha_documento")
            parametros["fecha_documento"] = filtros.fecha_documento
        return tuple(condiciones), parametros

    @staticmethod
    def _crear_clausula_where(condiciones: tuple[str, ...]) -> str:
        return f" WHERE {' AND '.join(condiciones)}" if condiciones else ""

    @staticmethod
    def _anidar_gestora(fila: dict[str, Any]) -> dict[str, Any]:
        datos = dict(fila)
        datos["gestora"] = {
            "codigo": datos.pop("gestora_codigo"),
            "nombre": datos.pop("gestora_nombre"),
        }
        return datos

    @staticmethod
    def _proteger(operacion: Callable[[], ResultadoT]) -> ResultadoT:
        try:
            return operacion()
        except ErrorRepositorio:
            raise
        except Exception as error:
            raise ErrorRepositorio(
                "No se han podido consultar los datos de fondos en Aurora."
            ) from error
