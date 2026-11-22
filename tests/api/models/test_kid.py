"""Pruebas de los modelos públicos de los documentos KID."""

import unittest
from datetime import date

from pydantic import ValidationError

from api.models.gestora import Gestora
from api.models.kid import KidVersion, RespuestaKids

SHA256_VALIDO = "0123456789abcdef" * 4

DATOS_KID = {
    "isin": "ES0123456789",
    "nombre_producto": "Bestinfond",
    "nombre_clase": "Clase C",
    "gestora": {"codigo": "bestinver", "nombre": "Bestinver"},
    "fecha_documento": "2026-11-19",
    "sri": 4,
    "periodo_mantenimiento_anios": 5,
    "gastos_corrientes_pct": 1.78,
    "costes_entrada_pct": 0,
    "costes_salida_pct": 0,
    "documento_sha256": SHA256_VALIDO,
}


class TestKidVersion(unittest.TestCase):
    def test_acepta_y_convierte_una_version_valida(self) -> None:
        kid = KidVersion(**DATOS_KID)

        self.assertIsInstance(kid.gestora, Gestora)
        self.assertEqual(kid.fecha_documento, date(2026, 11, 19))
        self.assertEqual(kid.documento_sha256, SHA256_VALIDO)
        self.assertEqual(kid.model_dump(mode="json")["fecha_documento"], "2026-11-19")

    def test_acepta_campos_nulos_pero_no_omitidos(self) -> None:
        campos_anulables = (
            "nombre_clase",
            "fecha_documento",
            "periodo_mantenimiento_anios",
            "gastos_corrientes_pct",
            "costes_entrada_pct",
            "costes_salida_pct",
        )
        datos_con_nulos = {**DATOS_KID, **dict.fromkeys(campos_anulables)}

        kid = KidVersion(**datos_con_nulos)
        self.assertIsNone(kid.fecha_documento)

        for campo in campos_anulables:
            datos_incompletos = {**DATOS_KID}
            del datos_incompletos[campo]
            with self.subTest(campo=campo), self.assertRaises(ValidationError):
                KidVersion(**datos_incompletos)

    def test_no_permite_un_sri_nulo(self) -> None:
        with self.assertRaises(ValidationError):
            KidVersion(**{**DATOS_KID, "sri": None})

    def test_rechaza_huellas_sha256_invalidas(self) -> None:
        huellas_invalidas = (
            "a" * 63,
            "A" * 64,
            "g" * 64,
        )

        for huella in huellas_invalidas:
            with self.subTest(huella=huella), self.assertRaises(ValidationError):
                KidVersion(**{**DATOS_KID, "documento_sha256": huella})

    def test_rechaza_campos_adicionales(self) -> None:
        with self.assertRaises(ValidationError):
            KidVersion(**DATOS_KID, evidencia="texto")


class TestRespuestaKids(unittest.TestCase):
    def test_valida_las_versiones_de_la_pagina(self) -> None:
        respuesta = RespuestaKids(
            datos=[DATOS_KID],
            paginacion={"pagina": 1, "tamano_pagina": 20, "total": 1},
        )

        self.assertIsInstance(respuesta.datos[0], KidVersion)
        self.assertEqual(respuesta.model_json_schema()["title"], "RespuestaKids")


if __name__ == "__main__":
    unittest.main()
