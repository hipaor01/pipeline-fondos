"""Pruebas de los modelos públicos de las gestoras."""

import unittest

from pydantic import ValidationError

from api.models.gestora import Gestora, RespuestaGestoras


class TestGestora(unittest.TestCase):
    def test_acepta_una_gestora_valida(self) -> None:
        gestora = Gestora(codigo="bestinver", nombre="Bestinver")

        self.assertEqual(gestora.codigo, "bestinver")
        self.assertEqual(gestora.nombre, "Bestinver")

    def test_rechaza_un_codigo_invalido(self) -> None:
        with self.assertRaises(ValidationError):
            Gestora(codigo="Bestinver España", nombre="Bestinver")

    def test_rechaza_un_nombre_vacio_o_demasiado_largo(self) -> None:
        for nombre in ("", "a" * 201):
            with self.subTest(nombre=nombre), self.assertRaises(ValidationError):
                Gestora(codigo="bestinver", nombre=nombre)

    def test_rechaza_campos_adicionales(self) -> None:
        with self.assertRaises(ValidationError):
            Gestora(codigo="bestinver", nombre="Bestinver", identificador=1)


class TestRespuestaGestoras(unittest.TestCase):
    def test_convierte_y_valida_las_gestoras_de_la_pagina(self) -> None:
        respuesta = RespuestaGestoras(
            datos=[{"codigo": "bestinver", "nombre": "Bestinver"}],
            paginacion={"pagina": 1, "tamano_pagina": 20, "total": 1},
        )

        self.assertIsInstance(respuesta.datos[0], Gestora)
        self.assertEqual(respuesta.datos[0].codigo, "bestinver")

    def test_conserva_el_nombre_del_esquema_openapi(self) -> None:
        esquema = RespuestaGestoras.model_json_schema()

        self.assertEqual(esquema["title"], "RespuestaGestoras")


if __name__ == "__main__":
    unittest.main()
