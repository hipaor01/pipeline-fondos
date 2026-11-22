"""Pruebas de los estados visibles de la aplicación Streamlit."""

import unittest

from streamlit.testing.v1 import AppTest


class TestEstadosAplicacion(unittest.TestCase):
    def test_error_muestra_trazabilidad_y_reintento(self) -> None:
        aplicacion = AppTest.from_string(
            """
from frontend.api_client import ErrorClienteAPI
from frontend.app import mostrar_error_api

mostrar_error_api(
    ErrorClienteAPI("No se ha podido conectar con la API.", "peticion-error"),
    clave_reintento="reintentar_prueba",
)
"""
        ).run()

        self.assertFalse(aplicacion.exception)
        self.assertEqual(
            aplicacion.error[0].value,
            "No se ha podido conectar con la API.",
        )
        self.assertIn("peticion-error", aplicacion.caption[0].value)
        self.assertEqual(aplicacion.button[0].label, "Reintentar")

    def test_historico_sin_versiones_muestra_estado_vacio(self) -> None:
        aplicacion = AppTest.from_string(
            """
from api.models import Paginacion, RespuestaKids
from frontend.api_client import ResultadoAPI
from frontend.app import mostrar_historico_kids

class ClienteSinKids:
    def listar_kids(self, **_filtros):
        return ResultadoAPI(
            datos=RespuestaKids(
                datos=[],
                paginacion=Paginacion(pagina=1, tamano_pagina=100, total=0),
            ),
            correlation_id="historico-vacio",
        )

mostrar_historico_kids(ClienteSinKids(), "ES0000000001")
"""
        ).run()

        self.assertFalse(aplicacion.exception)
        self.assertIn("No hay versiones KID", aplicacion.info[0].value)
        self.assertIn("0 versiones encontradas", aplicacion.caption[0].value)

    def test_listado_sin_datos_muestra_estados_vacios(self) -> None:
        aplicacion = AppTest.from_string(
            """
from api.models import Paginacion, RespuestaFondos, RespuestaGestoras
from frontend.api_client import ResultadoAPI
from frontend.app import mostrar_listado_fondos

class ClienteSinFondos:
    def listar_gestoras(self):
        return ResultadoAPI(
            datos=RespuestaGestoras(
                datos=[],
                paginacion=Paginacion(pagina=1, tamano_pagina=100, total=0),
            ),
            correlation_id="gestoras-vacias",
        )

    def listar_fondos(self, **_filtros):
        return ResultadoAPI(
            datos=RespuestaFondos(
                datos=[],
                paginacion=Paginacion(pagina=1, tamano_pagina=10, total=0),
            ),
            correlation_id="fondos-vacios",
        )

mostrar_listado_fondos(ClienteSinFondos())
"""
        ).run()

        self.assertFalse(aplicacion.exception)
        self.assertIn("No hay gestoras disponibles", aplicacion.warning[0].value)
        self.assertIn("No hay fondos", aplicacion.info[0].value)


if __name__ == "__main__":
    unittest.main()
