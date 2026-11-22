"""Pruebas del repositorio de fondos en memoria."""

import unittest
from datetime import date

from api.models.fondo import FondoDetalle
from api.repositories.base import ConsultaPaginada, FiltrosFondos, FiltrosKids
from api.repositories.memory import RepositorioFondosEnMemoria
from api.repositories.seed import crear_datos_semilla


class TestRepositorioFondosEnMemoria(unittest.TestCase):
    def setUp(self) -> None:
        self.repositorio = RepositorioFondosEnMemoria.con_datos_semilla()

    def test_lista_gestoras_ordenadas_y_paginadas(self) -> None:
        resultado = self.repositorio.listar_gestoras(
            ConsultaPaginada(pagina=2, tamano_pagina=2)
        )

        self.assertEqual(resultado.total, 3)
        self.assertEqual(
            [gestora.codigo for gestora in resultado.elementos], ["cobas-am"]
        )

    def test_filtra_fondos_por_gestora_nombre_e_isin(self) -> None:
        por_gestora = self.repositorio.listar_fondos(
            FiltrosFondos(gestora="bestinver"),
            ConsultaPaginada(),
        )
        por_nombre = self.repositorio.listar_fondos(
            FiltrosFondos(nombre="INTERNACIONAL"),
            ConsultaPaginada(),
        )
        por_isin = self.repositorio.listar_fondos(
            FiltrosFondos(isin="ES0000000003"),
            ConsultaPaginada(),
        )

        self.assertEqual(por_gestora.total, 2)
        self.assertEqual(por_nombre.total, 3)
        self.assertEqual(por_isin.total, 1)
        self.assertEqual(por_isin.elementos[0].nombre_producto, "Azvalor Internacional")

    def test_ordena_fondos_por_nombre_e_isin(self) -> None:
        resultado = self.repositorio.listar_fondos(
            FiltrosFondos(),
            ConsultaPaginada(),
        )

        nombres = [fondo.nombre_producto for fondo in resultado.elementos]
        self.assertEqual(
            nombres,
            [
                "Azvalor Internacional",
                "Bestinfond",
                "Bestinver Internacional",
                "Cobas Internacional",
                "Cobas Selección",
            ],
        )

    def test_obtiene_un_fondo_o_none(self) -> None:
        fondo = self.repositorio.obtener_fondo("ES0000000001")

        self.assertIsInstance(fondo, FondoDetalle)
        self.assertIsNone(self.repositorio.obtener_fondo("ES9999999999"))

    def test_devuelve_copias_para_no_exponer_el_estado_interno(self) -> None:
        fondo = self.repositorio.obtener_fondo("ES0000000001")
        assert fondo is not None
        fondo.nombre_producto = "Nombre modificado"

        fondo_sin_modificar = self.repositorio.obtener_fondo("ES0000000001")
        assert fondo_sin_modificar is not None
        self.assertEqual(fondo_sin_modificar.nombre_producto, "Bestinfond")

    def test_filtra_y_ordena_versiones_kid(self) -> None:
        todos = self.repositorio.listar_kids(
            FiltrosKids(),
            ConsultaPaginada(),
        )
        por_fecha = self.repositorio.listar_kids(
            FiltrosKids(fecha_documento=date(2026, 11, 19)),
            ConsultaPaginada(),
        )
        por_gestora_e_isin = self.repositorio.listar_kids(
            FiltrosKids(gestora="bestinver", isin="ES0000000001"),
            ConsultaPaginada(),
        )

        self.assertEqual(todos.total, 6)
        self.assertEqual(todos.elementos[0].fecha_documento, date(2026, 11, 19))
        self.assertIsNone(todos.elementos[-1].fecha_documento)
        self.assertEqual(por_fecha.total, 1)
        self.assertEqual(por_gestora_e_isin.total, 2)

    def test_rechaza_identificadores_duplicados(self) -> None:
        gestoras, fondos, kids = crear_datos_semilla()

        with self.assertRaisesRegex(ValueError, "Código de gestora duplicado"):
            RepositorioFondosEnMemoria(
                gestoras=(*gestoras, gestoras[0]),
                fondos=fondos,
                kids=kids,
            )

        with self.assertRaisesRegex(ValueError, "SHA-256 de documento KID duplicado"):
            RepositorioFondosEnMemoria(
                gestoras=gestoras,
                fondos=fondos,
                kids=(*kids, kids[0]),
            )

    def test_rechaza_un_kid_sin_fondo_asociado(self) -> None:
        gestoras, fondos, kids = crear_datos_semilla()

        with self.assertRaisesRegex(ValueError, "no tiene fondo asociado"):
            RepositorioFondosEnMemoria(
                gestoras=gestoras,
                fondos=fondos[1:],
                kids=kids,
            )


if __name__ == "__main__":
    unittest.main()
