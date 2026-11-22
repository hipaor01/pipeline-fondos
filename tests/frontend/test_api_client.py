"""Pruebas unitarias del cliente utilizado por Streamlit."""

import unittest
from datetime import date

import httpx2

from frontend.api_client import ClienteAPI, ErrorClienteAPI


class TestClienteAPI(unittest.TestCase):
    def test_obtiene_y_valida_el_estado(self) -> None:
        def responder(peticion: httpx2.Request) -> httpx2.Response:
            self.assertTrue(
                peticion.headers["X-Correlation-Id"].startswith("streamlit-")
            )
            return httpx2.Response(
                200,
                json={
                    "estado": "ok",
                    "servicio": "api-fondos",
                    "version": "0.1.0",
                },
                headers={"X-Correlation-Id": "prueba-health"},
            )

        cliente = ClienteAPI(
            "http://api.example.test",
            1,
            transport=httpx2.MockTransport(responder),
        )
        self.addCleanup(cliente.cerrar)

        resultado = cliente.obtener_estado()

        self.assertEqual(resultado.datos.servicio, "api-fondos")
        self.assertEqual(resultado.correlation_id, "prueba-health")

    def test_lista_gestoras_con_paginacion(self) -> None:
        def responder(peticion: httpx2.Request) -> httpx2.Response:
            self.assertEqual(
                dict(peticion.url.params),
                {"pagina": "1", "tamano_pagina": "100"},
            )
            return httpx2.Response(
                200,
                json={
                    "datos": [{"codigo": "bestinver", "nombre": "Bestinver"}],
                    "paginacion": {
                        "pagina": 1,
                        "tamano_pagina": 100,
                        "total": 1,
                    },
                },
            )

        cliente = ClienteAPI(
            "http://api.example.test",
            1,
            transport=httpx2.MockTransport(responder),
        )
        self.addCleanup(cliente.cerrar)

        resultado = cliente.listar_gestoras()

        self.assertEqual(resultado.datos.datos[0].codigo, "bestinver")

    def test_lista_fondos_con_filtros_y_paginacion(self) -> None:
        def responder(peticion: httpx2.Request) -> httpx2.Response:
            self.assertEqual(
                dict(peticion.url.params),
                {
                    "pagina": "2",
                    "tamano_pagina": "10",
                    "gestora": "bestinver",
                    "isin": "ES0000000001",
                    "nombre": "Bestinfond",
                },
            )
            return httpx2.Response(
                200,
                json={
                    "datos": [
                        {
                            "isin": "ES0000000001",
                            "nombre_producto": "Bestinfond",
                            "nombre_clase": "Clase C",
                            "gestora": {
                                "codigo": "bestinver",
                                "nombre": "Bestinver",
                            },
                            "fecha_ultimo_kid": "2026-11-19",
                            "sri": 4,
                        }
                    ],
                    "paginacion": {
                        "pagina": 2,
                        "tamano_pagina": 10,
                        "total": 11,
                    },
                },
            )

        cliente = ClienteAPI(
            "http://api.example.test",
            1,
            transport=httpx2.MockTransport(responder),
        )
        self.addCleanup(cliente.cerrar)

        resultado = cliente.listar_fondos(
            pagina=2,
            tamano_pagina=10,
            gestora="bestinver",
            isin="ES0000000001",
            nombre="Bestinfond",
        )

        self.assertEqual(resultado.datos.paginacion.total, 11)
        self.assertEqual(resultado.datos.datos[0].isin, "ES0000000001")

    def test_obtiene_el_detalle_de_un_fondo_por_isin(self) -> None:
        def responder(peticion: httpx2.Request) -> httpx2.Response:
            self.assertEqual(peticion.url.path, "/fondos/ES0000000001")
            return httpx2.Response(
                200,
                json={
                    "isin": "ES0000000001",
                    "nombre_producto": "Bestinfond",
                    "nombre_clase": "Clase C",
                    "gestora": {
                        "codigo": "bestinver",
                        "nombre": "Bestinver",
                    },
                    "fecha_ultimo_kid": "2026-11-19",
                    "sri": 4,
                    "periodo_mantenimiento_anios": 5,
                    "gastos_corrientes_pct": 1.78,
                    "costes_entrada_pct": 0,
                    "costes_salida_pct": 0,
                },
                headers={"X-Correlation-Id": "detalle-bestinfond"},
            )

        cliente = ClienteAPI(
            "http://api.example.test",
            1,
            transport=httpx2.MockTransport(responder),
        )
        self.addCleanup(cliente.cerrar)

        resultado = cliente.obtener_fondo("ES0000000001")

        self.assertEqual(resultado.datos.nombre_producto, "Bestinfond")
        self.assertEqual(resultado.datos.gastos_corrientes_pct, 1.78)
        self.assertEqual(resultado.correlation_id, "detalle-bestinfond")

    def test_lista_el_historico_kid_con_filtros(self) -> None:
        def responder(peticion: httpx2.Request) -> httpx2.Response:
            self.assertEqual(peticion.url.path, "/kids")
            self.assertEqual(
                dict(peticion.url.params),
                {
                    "pagina": "1",
                    "tamano_pagina": "100",
                    "gestora": "bestinver",
                    "isin": "ES0000000001",
                    "fecha": "2026-11-19",
                },
            )
            return httpx2.Response(
                200,
                json={
                    "datos": [
                        {
                            "isin": "ES0000000001",
                            "nombre_producto": "Bestinfond",
                            "nombre_clase": "Clase C",
                            "gestora": {
                                "codigo": "bestinver",
                                "nombre": "Bestinver",
                            },
                            "fecha_documento": "2026-11-19",
                            "sri": 4,
                            "periodo_mantenimiento_anios": 5,
                            "gastos_corrientes_pct": 1.78,
                            "costes_entrada_pct": 0,
                            "costes_salida_pct": 0,
                            "documento_sha256": "a" * 64,
                        }
                    ],
                    "paginacion": {
                        "pagina": 1,
                        "tamano_pagina": 100,
                        "total": 1,
                    },
                },
                headers={"X-Correlation-Id": "historico-bestinfond"},
            )

        cliente = ClienteAPI(
            "http://api.example.test",
            1,
            transport=httpx2.MockTransport(responder),
        )
        self.addCleanup(cliente.cerrar)

        resultado = cliente.listar_kids(
            gestora="bestinver",
            isin="ES0000000001",
            fecha=date(2026, 11, 19),
        )

        self.assertEqual(resultado.datos.paginacion.total, 1)
        self.assertEqual(resultado.datos.datos[0].documento_sha256, "a" * 64)
        self.assertEqual(resultado.correlation_id, "historico-bestinfond")

    def test_rechaza_una_respuesta_que_incumple_el_contrato(self) -> None:
        cliente = ClienteAPI(
            "http://api.example.test",
            1,
            transport=httpx2.MockTransport(
                lambda _peticion: httpx2.Response(
                    200,
                    json={"estado": "desconocido"},
                )
            ),
        )
        self.addCleanup(cliente.cerrar)

        with self.assertRaisesRegex(ErrorClienteAPI, "formato inesperado"):
            cliente.obtener_estado()

    def test_convierte_el_error_publico_de_la_api(self) -> None:
        cliente = ClienteAPI(
            "http://api.example.test",
            1,
            transport=httpx2.MockTransport(
                lambda _peticion: httpx2.Response(
                    500,
                    json={
                        "codigo": "ERROR_INTERNO",
                        "mensaje": "No se ha podido completar la consulta.",
                        "correlation_id": "error-api",
                        "detalles": [],
                    },
                    headers={"X-Correlation-Id": "error-api"},
                )
            ),
        )
        self.addCleanup(cliente.cerrar)

        with self.assertRaisesRegex(
            ErrorClienteAPI,
            "No se ha podido completar la consulta",
        ) as contexto:
            cliente.obtener_estado()

        self.assertEqual(contexto.exception.correlation_id, "error-api")


if __name__ == "__main__":
    unittest.main()
