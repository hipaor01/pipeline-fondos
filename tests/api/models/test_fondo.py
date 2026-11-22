"""Pruebas de los modelos públicos de los fondos."""

import unittest
from datetime import date
from math import inf, nan

from pydantic import ValidationError

from api.models.fondo import FondoDetalle, FondoResumen, RespuestaFondos
from api.models.gestora import Gestora

DATOS_FONDO = {
    "isin": "ES0123456789",
    "nombre_producto": "Bestinfond",
    "nombre_clase": "Clase C",
    "gestora": {"codigo": "bestinver", "nombre": "Bestinver"},
    "fecha_ultimo_kid": "2026-11-19",
    "sri": 4,
}


class TestFondoResumen(unittest.TestCase):
    def test_acepta_y_convierte_un_fondo_valido(self) -> None:
        fondo = FondoResumen(**DATOS_FONDO)

        self.assertIsInstance(fondo.gestora, Gestora)
        self.assertEqual(fondo.fecha_ultimo_kid, date(2026, 11, 19))
        self.assertEqual(fondo.sri, 4)

    def test_acepta_campos_nulos_pero_no_omitidos(self) -> None:
        datos_con_nulos = {
            **DATOS_FONDO,
            "nombre_clase": None,
            "fecha_ultimo_kid": None,
            "sri": None,
        }

        fondo = FondoResumen(**datos_con_nulos)
        self.assertIsNone(fondo.nombre_clase)

        for campo in ("nombre_clase", "fecha_ultimo_kid", "sri"):
            datos_incompletos = {**DATOS_FONDO}
            del datos_incompletos[campo]
            with self.subTest(campo=campo), self.assertRaises(ValidationError):
                FondoResumen(**datos_incompletos)

    def test_rechaza_nombres_y_sri_fuera_del_contrato(self) -> None:
        casos = (
            {**DATOS_FONDO, "nombre_producto": ""},
            {**DATOS_FONDO, "nombre_producto": "a" * 301},
            {**DATOS_FONDO, "nombre_clase": "a" * 201},
            {**DATOS_FONDO, "sri": 0},
            {**DATOS_FONDO, "sri": 8},
        )

        for caso in casos:
            with self.subTest(caso=caso), self.assertRaises(ValidationError):
                FondoResumen(**caso)

    def test_rechaza_campos_adicionales(self) -> None:
        with self.assertRaises(ValidationError):
            FondoResumen(**DATOS_FONDO, rentabilidad=10.5)


class TestFondoDetalle(unittest.TestCase):
    def test_acepta_un_detalle_valido(self) -> None:
        fondo = FondoDetalle(
            **DATOS_FONDO,
            periodo_mantenimiento_anios=5,
            gastos_corrientes_pct=1.78,
            costes_entrada_pct=0,
            costes_salida_pct=None,
        )

        self.assertEqual(fondo.gastos_corrientes_pct, 1.78)
        self.assertIsNone(fondo.costes_salida_pct)

    def test_requiere_los_campos_de_detalle_aunque_sean_nulos(self) -> None:
        with self.assertRaises(ValidationError):
            FondoDetalle(**DATOS_FONDO)

    def test_rechaza_valores_negativos_o_no_finitos(self) -> None:
        for valor in (-0.01, inf, nan):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                FondoDetalle(
                    **DATOS_FONDO,
                    periodo_mantenimiento_anios=5,
                    gastos_corrientes_pct=valor,
                    costes_entrada_pct=0,
                    costes_salida_pct=0,
                )


class TestRespuestaFondos(unittest.TestCase):
    def test_valida_los_fondos_de_la_pagina(self) -> None:
        respuesta = RespuestaFondos(
            datos=[DATOS_FONDO],
            paginacion={"pagina": 1, "tamano_pagina": 20, "total": 1},
        )

        self.assertIsInstance(respuesta.datos[0], FondoResumen)
        self.assertEqual(respuesta.model_json_schema()["title"], "RespuestaFondos")


if __name__ == "__main__":
    unittest.main()
