"""Pruebas del repositorio de lectura sobre Aurora."""

import unittest
from datetime import date
from typing import Any

from api.models.fondo import FondoDetalle, FondoResumen
from api.models.gestora import Gestora
from api.models.kid import KidVersion
from api.repositories.aurora import RepositorioFondosAurora
from api.repositories.base import (
    ConsultaPaginada,
    ErrorRepositorio,
    FiltrosFondos,
    FiltrosKids,
)
from database.ejecutor import Parametros


class EjecutorSQLFalso:
    def __init__(self, *respuestas: list[dict[str, Any]] | Exception) -> None:
        self._respuestas = list(respuestas)
        self.llamadas: list[tuple[str, Parametros | None]] = []

    def ejecutar(
        self,
        sql: str,
        parametros: Parametros | None = None,
    ) -> list[dict[str, Any]]:
        self.llamadas.append((sql, parametros))
        respuesta = self._respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta

    def transaccion(self) -> Any:
        raise AssertionError("El repositorio de lectura no debe abrir transacciones.")


FILA_FONDO = {
    "isin": "ES0000000001",
    "nombre_producto": "Bestinfond",
    "nombre_clase": "Clase C",
    "gestora_codigo": "bestinver",
    "gestora_nombre": "Bestinver",
    "fecha_ultimo_kid": "2026-11-19",
    "sri": 4,
}

FILA_DETALLE = {
    **FILA_FONDO,
    "periodo_mantenimiento_anios": 5.0,
    "gastos_corrientes_pct": 1.78,
    "costes_entrada_pct": 0.0,
    "costes_salida_pct": 0.0,
}

FILA_KID = {
    "isin": "ES0000000001",
    "nombre_producto": "Bestinfond",
    "nombre_clase": "Clase C",
    "gestora_codigo": "bestinver",
    "gestora_nombre": "Bestinver",
    "fecha_documento": "2026-11-19",
    "sri": 4,
    "periodo_mantenimiento_anios": 5.0,
    "gastos_corrientes_pct": 1.78,
    "costes_entrada_pct": 0.0,
    "costes_salida_pct": 0.0,
    "documento_sha256": "a" * 64,
}


class TestRepositorioFondosAurora(unittest.TestCase):
    def test_lista_gestoras_ordenadas_y_paginadas(self) -> None:
        ejecutor = EjecutorSQLFalso(
            [{"total": 3}],
            [{"codigo": "cobas", "nombre": "Cobas AM"}],
        )
        repositorio = RepositorioFondosAurora(ejecutor)

        resultado = repositorio.listar_gestoras(
            ConsultaPaginada(pagina=2, tamano_pagina=2)
        )

        self.assertEqual(resultado.total, 3)
        self.assertEqual(
            resultado.elementos,
            (Gestora(codigo="cobas", nombre="Cobas AM"),),
        )
        sql_datos, parametros = ejecutor.llamadas[1]
        self.assertIn("ORDER BY lower(nombre), codigo", sql_datos)
        self.assertEqual(parametros, {"limite": 2, "desplazamiento": 2})

    def test_lista_fondos_aplicando_todos_los_filtros(self) -> None:
        ejecutor = EjecutorSQLFalso([{"total": 1}], [FILA_FONDO])
        repositorio = RepositorioFondosAurora(ejecutor)
        filtros = FiltrosFondos(
            gestora="bestinver",
            isin="ES0000000001",
            nombre="BEST%_",
        )

        resultado = repositorio.listar_fondos(filtros, ConsultaPaginada())

        self.assertEqual(resultado.total, 1)
        self.assertIsInstance(resultado.elementos[0], FondoResumen)
        self.assertEqual(resultado.elementos[0].gestora.codigo, "bestinver")
        sql_total, parametros_total = ejecutor.llamadas[0]
        self.assertIn("gestora_codigo = :gestora", sql_total)
        self.assertIn("isin = :isin", sql_total)
        self.assertIn("strpos(lower(nombre_producto), lower(:nombre)) > 0", sql_total)
        self.assertNotIn("BEST%_", sql_total)
        self.assertEqual(
            parametros_total,
            {
                "gestora": "bestinver",
                "isin": "ES0000000001",
                "nombre": "BEST%_",
            },
        )
        self.assertIn("ORDER BY lower(nombre_producto), isin", ejecutor.llamadas[1][0])

    def test_obtiene_el_detalle_de_un_fondo(self) -> None:
        ejecutor = EjecutorSQLFalso([FILA_DETALLE])
        repositorio = RepositorioFondosAurora(ejecutor)

        fondo = repositorio.obtener_fondo("ES0000000001")

        self.assertIsInstance(fondo, FondoDetalle)
        assert fondo is not None
        self.assertEqual(fondo.fecha_ultimo_kid, date(2026, 11, 19))
        self.assertEqual(fondo.gastos_corrientes_pct, 1.78)
        self.assertEqual(ejecutor.llamadas[0][1], {"isin": "ES0000000001"})

    def test_devuelve_none_si_el_fondo_no_existe(self) -> None:
        repositorio = RepositorioFondosAurora(EjecutorSQLFalso([]))

        self.assertIsNone(repositorio.obtener_fondo("ES9999999999"))

    def test_lista_kids_aplicando_filtros_y_orden_contractual(self) -> None:
        ejecutor = EjecutorSQLFalso([{"total": 1}], [FILA_KID])
        repositorio = RepositorioFondosAurora(ejecutor)
        filtros = FiltrosKids(
            gestora="bestinver",
            isin="ES0000000001",
            fecha_documento=date(2026, 11, 19),
        )

        resultado = repositorio.listar_kids(filtros, ConsultaPaginada())

        self.assertIsInstance(resultado.elementos[0], KidVersion)
        sql_datos, parametros = ejecutor.llamadas[1]
        self.assertIn(
            "ORDER BY fecha_documento DESC NULLS LAST, isin, documento_sha256",
            sql_datos,
        )
        self.assertEqual(parametros["fecha_documento"], date(2026, 11, 19))

    def test_traduce_errores_del_ejecutor(self) -> None:
        error_sql = RuntimeError("El secreto no es accesible")
        repositorio = RepositorioFondosAurora(EjecutorSQLFalso(error_sql))

        with self.assertRaises(ErrorRepositorio) as contexto:
            repositorio.listar_gestoras(ConsultaPaginada())

        self.assertIs(contexto.exception.__cause__, error_sql)
        self.assertNotIn("secreto", str(contexto.exception).lower())

    def test_traduce_filas_invalidas_a_error_de_repositorio(self) -> None:
        repositorio = RepositorioFondosAurora(
            EjecutorSQLFalso([{"total": 1}], [{"codigo": "INVALIDO"}])
        )

        with self.assertRaises(ErrorRepositorio):
            repositorio.listar_gestoras(ConsultaPaginada())


if __name__ == "__main__":
    unittest.main()
