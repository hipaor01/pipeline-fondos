"""Pruebas de los tipos y modelos compartidos de la API."""

import unittest

from pydantic import ValidationError

from api.models.common import (
    CodigoGestora,
    Isin,
    ModeloAPI,
    Paginacion,
    RespuestaPaginada,
)


class RecursoConIdentificadores(ModeloAPI):
    isin: Isin
    gestora: CodigoGestora


class ElementoPrueba(ModeloAPI):
    nombre: str


class TestTiposComunes(unittest.TestCase):
    def test_acepta_identificadores_validos(self) -> None:
        recurso = RecursoConIdentificadores(
            isin="ES0123456789",
            gestora="bestinver",
        )

        self.assertEqual(recurso.isin, "ES0123456789")
        self.assertEqual(recurso.gestora, "bestinver")

    def test_rechaza_isin_invalido(self) -> None:
        with self.assertRaises(ValidationError):
            RecursoConIdentificadores(
                isin="ES123",
                gestora="bestinver",
            )

    def test_rechaza_codigo_gestora_invalido(self) -> None:
        with self.assertRaises(ValidationError):
            RecursoConIdentificadores(
                isin="ES0123456789",
                gestora="Bestinver España",
            )


class TestPaginacion(unittest.TestCase):
    def test_acepta_limites_validos(self) -> None:
        paginacion = Paginacion(pagina=1, tamano_pagina=100, total=0)

        self.assertEqual(paginacion.pagina, 1)
        self.assertEqual(paginacion.tamano_pagina, 100)
        self.assertEqual(paginacion.total, 0)

    def test_rechaza_valores_fuera_de_rango(self) -> None:
        casos = (
            {"pagina": 0, "tamano_pagina": 20, "total": 1},
            {"pagina": 1, "tamano_pagina": 101, "total": 1},
            {"pagina": 1, "tamano_pagina": 20, "total": -1},
        )

        for caso in casos:
            with self.subTest(caso=caso), self.assertRaises(ValidationError):
                Paginacion(**caso)

    def test_rechaza_campos_adicionales(self) -> None:
        with self.assertRaises(ValidationError):
            Paginacion(
                pagina=1,
                tamano_pagina=20,
                total=1,
                paginas_totales=1,
            )


class TestRespuestaPaginada(unittest.TestCase):
    def test_valida_el_tipo_de_los_elementos(self) -> None:
        respuesta = RespuestaPaginada[ElementoPrueba](
            datos=[{"nombre": "Fondo de prueba"}],
            paginacion={"pagina": 1, "tamano_pagina": 20, "total": 1},
        )

        self.assertIsInstance(respuesta.datos[0], ElementoPrueba)
        self.assertIsInstance(respuesta.paginacion, Paginacion)

    def test_requiere_los_metadatos_de_paginacion(self) -> None:
        with self.assertRaises(ValidationError):
            RespuestaPaginada[ElementoPrueba](datos=[])


if __name__ == "__main__":
    unittest.main()
