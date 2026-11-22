"""Pruebas de la interfaz y los tipos del repositorio."""

import unittest
from dataclasses import FrozenInstanceError

from api.models.common import Isin
from api.models.fondo import FondoDetalle, FondoResumen
from api.models.gestora import Gestora
from api.models.kid import KidVersion
from api.repositories.base import (
    ConsultaPaginada,
    FiltrosFondos,
    FiltrosKids,
    RepositorioFondos,
    ResultadoPaginado,
)


class RepositorioPrueba(RepositorioFondos):
    def listar_gestoras(
        self,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[Gestora]:
        return ResultadoPaginado(elementos=(), total=0)

    def listar_fondos(
        self,
        filtros: FiltrosFondos,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[FondoResumen]:
        return ResultadoPaginado(elementos=(), total=0)

    def obtener_fondo(self, isin: Isin) -> FondoDetalle | None:
        return None

    def listar_kids(
        self,
        filtros: FiltrosKids,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[KidVersion]:
        return ResultadoPaginado(elementos=(), total=0)


class RepositorioIncompleto(RepositorioFondos):
    pass


class TestConsultaPaginada(unittest.TestCase):
    def test_utiliza_los_valores_por_defecto(self) -> None:
        consulta = ConsultaPaginada()

        self.assertEqual(consulta.pagina, 1)
        self.assertEqual(consulta.tamano_pagina, 20)
        self.assertEqual(consulta.desplazamiento, 0)

    def test_calcula_el_desplazamiento(self) -> None:
        consulta = ConsultaPaginada(pagina=3, tamano_pagina=25)

        self.assertEqual(consulta.desplazamiento, 50)

    def test_rechaza_valores_fuera_de_rango(self) -> None:
        casos = (
            {"pagina": 0, "tamano_pagina": 20},
            {"pagina": 1, "tamano_pagina": 0},
            {"pagina": 1, "tamano_pagina": 101},
        )

        for caso in casos:
            with self.subTest(caso=caso), self.assertRaises(ValueError):
                ConsultaPaginada(**caso)

    def test_rechaza_tipos_que_no_sean_enteros(self) -> None:
        for pagina in (True, 1.5, "1"):
            with self.subTest(pagina=pagina), self.assertRaises(TypeError):
                ConsultaPaginada(pagina=pagina)


class TestFiltros(unittest.TestCase):
    def test_son_inmutables(self) -> None:
        filtros = FiltrosFondos(gestora="bestinver")

        with self.assertRaises(FrozenInstanceError):
            filtros.gestora = "otra-gestora"


class TestResultadoPaginado(unittest.TestCase):
    def test_acepta_un_resultado_coherente(self) -> None:
        resultado = ResultadoPaginado(elementos=("a", "b"), total=5)

        self.assertEqual(resultado.elementos, ("a", "b"))
        self.assertEqual(resultado.total, 5)

    def test_rechaza_un_total_invalido(self) -> None:
        for total in (-1, 1):
            with self.subTest(total=total), self.assertRaises(ValueError):
                ResultadoPaginado(elementos=("a", "b"), total=total)


class TestRepositorioFondos(unittest.TestCase):
    def test_permite_implementar_todas_las_operaciones(self) -> None:
        repositorio = RepositorioPrueba()

        resultado = repositorio.listar_gestoras(ConsultaPaginada())
        self.assertEqual(resultado.total, 0)

    def test_no_permite_instanciar_una_implementacion_incompleta(self) -> None:
        with self.assertRaises(TypeError):
            RepositorioIncompleto()


if __name__ == "__main__":
    unittest.main()
