"""Pruebas de la capa de servicio de fondos."""

import unittest
from datetime import date
from unittest.mock import create_autospec

from api.models.fondo import FondoDetalle, FondoResumen, RespuestaFondos
from api.models.gestora import Gestora, RespuestaGestoras
from api.models.kid import KidVersion, RespuestaKids
from api.repositories.base import (
    ConsultaPaginada,
    ErrorRepositorio,
    FiltrosFondos,
    FiltrosKids,
    RepositorioFondos,
    ResultadoPaginado,
)
from api.repositories.memory import RepositorioFondosEnMemoria
from api.services.errors import FondoNoEncontrado
from api.services.fondos import ServicioFondos

GESTORA = Gestora(codigo="bestinver", nombre="Bestinver")
FONDO_RESUMEN = FondoResumen(
    isin="ES0000000001",
    nombre_producto="Bestinfond",
    nombre_clase="Clase C",
    gestora=GESTORA,
    fecha_ultimo_kid=date(2026, 11, 19),
    sri=4,
)
FONDO_DETALLE = FondoDetalle(
    **FONDO_RESUMEN.model_dump(),
    periodo_mantenimiento_anios=5,
    gastos_corrientes_pct=1.78,
    costes_entrada_pct=0,
    costes_salida_pct=0,
)
KID = KidVersion(
    isin=FONDO_RESUMEN.isin,
    nombre_producto=FONDO_RESUMEN.nombre_producto,
    nombre_clase=FONDO_RESUMEN.nombre_clase,
    gestora=GESTORA,
    fecha_documento=date(2026, 11, 19),
    sri=4,
    periodo_mantenimiento_anios=5,
    gastos_corrientes_pct=1.78,
    costes_entrada_pct=0,
    costes_salida_pct=0,
    documento_sha256="a" * 64,
)


class TestServicioFondos(unittest.TestCase):
    def setUp(self) -> None:
        self.repositorio = create_autospec(RepositorioFondos, instance=True)
        self.servicio = ServicioFondos(self.repositorio)

    def test_convierte_el_resultado_de_gestoras(self) -> None:
        paginacion = ConsultaPaginada(pagina=2, tamano_pagina=10)
        self.repositorio.listar_gestoras.return_value = ResultadoPaginado(
            elementos=(GESTORA,),
            total=21,
        )

        respuesta = self.servicio.listar_gestoras(paginacion)

        self.assertIsInstance(respuesta, RespuestaGestoras)
        self.assertEqual(respuesta.datos, [GESTORA])
        self.assertEqual(respuesta.paginacion.pagina, 2)
        self.assertEqual(respuesta.paginacion.tamano_pagina, 10)
        self.assertEqual(respuesta.paginacion.total, 21)
        self.repositorio.listar_gestoras.assert_called_once_with(paginacion)

    def test_convierte_el_resultado_de_fondos_y_delega_los_filtros(self) -> None:
        filtros = FiltrosFondos(gestora="bestinver")
        paginacion = ConsultaPaginada()
        self.repositorio.listar_fondos.return_value = ResultadoPaginado(
            elementos=(FONDO_RESUMEN,),
            total=1,
        )

        respuesta = self.servicio.listar_fondos(filtros, paginacion)

        self.assertIsInstance(respuesta, RespuestaFondos)
        self.assertEqual(respuesta.datos, [FONDO_RESUMEN])
        self.repositorio.listar_fondos.assert_called_once_with(filtros, paginacion)

    def test_devuelve_el_detalle_de_un_fondo_existente(self) -> None:
        self.repositorio.obtener_fondo.return_value = FONDO_DETALLE

        fondo = self.servicio.obtener_fondo(FONDO_DETALLE.isin)

        self.assertEqual(fondo, FONDO_DETALLE)
        self.repositorio.obtener_fondo.assert_called_once_with(FONDO_DETALLE.isin)

    def test_lanza_un_error_especifico_si_el_fondo_no_existe(self) -> None:
        isin = "ES9999999999"
        self.repositorio.obtener_fondo.return_value = None

        with self.assertRaises(FondoNoEncontrado) as contexto:
            self.servicio.obtener_fondo(isin)

        self.assertEqual(contexto.exception.isin, isin)
        self.assertEqual(contexto.exception.codigo, "FONDO_NO_ENCONTRADO")

    def test_convierte_el_resultado_de_kids(self) -> None:
        filtros = FiltrosKids(fecha_documento=date(2026, 11, 19))
        paginacion = ConsultaPaginada()
        self.repositorio.listar_kids.return_value = ResultadoPaginado(
            elementos=(KID,),
            total=1,
        )

        respuesta = self.servicio.listar_kids(filtros, paginacion)

        self.assertIsInstance(respuesta, RespuestaKids)
        self.assertEqual(respuesta.datos, [KID])
        self.repositorio.listar_kids.assert_called_once_with(filtros, paginacion)

    def test_no_oculta_los_errores_tecnicos_del_repositorio(self) -> None:
        self.repositorio.listar_gestoras.side_effect = ErrorRepositorio(
            "No se ha podido consultar la fuente de datos."
        )

        with self.assertRaises(ErrorRepositorio):
            self.servicio.listar_gestoras(ConsultaPaginada())


class TestIntegracionServicioConMemoria(unittest.TestCase):
    def test_consulta_los_datos_semilla_a_traves_del_servicio(self) -> None:
        servicio = ServicioFondos(RepositorioFondosEnMemoria.con_datos_semilla())

        respuesta = servicio.listar_fondos(
            FiltrosFondos(gestora="bestinver"),
            ConsultaPaginada(),
        )
        fondo = servicio.obtener_fondo("ES0000000001")

        self.assertEqual(respuesta.paginacion.total, 2)
        self.assertEqual(fondo.nombre_producto, "Bestinfond")


if __name__ == "__main__":
    unittest.main()
