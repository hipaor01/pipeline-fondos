"""Pruebas HTTP de la aplicación FastAPI."""

import unittest
from unittest.mock import create_autospec
from uuid import UUID

from fastapi.testclient import TestClient

from api.app import crear_aplicacion
from api.repositories.base import ErrorRepositorio
from api.services.fondos import ServicioFondos


class TestAplicacionFastAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.cliente = TestClient(crear_aplicacion())

    def tearDown(self) -> None:
        self.cliente.close()

    def test_health_devuelve_estado_y_correlation_id(self) -> None:
        respuesta = self.cliente.get("/health")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.json(),
            {"estado": "ok", "servicio": "api-fondos", "version": "0.1.0"},
        )
        UUID(respuesta.headers["X-Correlation-Id"])

    def test_propaga_el_correlation_id_del_cliente(self) -> None:
        correlation_id = "peticion-streamlit-123"

        respuesta = self.cliente.get(
            "/gestoras",
            headers={"X-Correlation-Id": correlation_id},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.headers["X-Correlation-Id"], correlation_id)

    def test_lista_gestoras_con_paginacion(self) -> None:
        respuesta = self.cliente.get(
            "/gestoras",
            params={"pagina": 2, "tamano_pagina": 2},
        )

        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertEqual(
            cuerpo["paginacion"], {"pagina": 2, "tamano_pagina": 2, "total": 3}
        )
        self.assertEqual(
            [gestora["codigo"] for gestora in cuerpo["datos"]], ["cobas-am"]
        )

    def test_lista_y_filtra_fondos(self) -> None:
        respuesta = self.cliente.get(
            "/fondos",
            params={"gestora": "bestinver", "nombre": "INTERNACIONAL"},
        )

        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["paginacion"]["total"], 1)
        self.assertEqual(cuerpo["datos"][0]["isin"], "ES0000000002")

    def test_obtiene_el_detalle_de_un_fondo(self) -> None:
        respuesta = self.cliente.get("/fondos/ES0000000001")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["nombre_producto"], "Bestinfond")

    def test_fondo_inexistente_devuelve_el_error_publico(self) -> None:
        correlation_id = "consulta-fondo-inexistente"

        respuesta = self.cliente.get(
            "/fondos/ES9999999999",
            headers={"X-Correlation-Id": correlation_id},
        )

        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(
            respuesta.json(),
            {
                "codigo": "FONDO_NO_ENCONTRADO",
                "mensaje": "No existe ningún fondo con el ISIN ES9999999999.",
                "correlation_id": correlation_id,
                "detalles": [],
            },
        )
        self.assertEqual(respuesta.headers["X-Correlation-Id"], correlation_id)

    def test_lista_kids_filtrados_por_fecha(self) -> None:
        respuesta = self.cliente.get(
            "/kids",
            params={"fecha": "2026-11-19"},
        )

        self.assertEqual(respuesta.status_code, 200)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["paginacion"]["total"], 1)
        self.assertEqual(cuerpo["datos"][0]["fecha_documento"], "2026-11-19")

    def test_parametro_invalido_devuelve_el_modelo_error(self) -> None:
        respuesta = self.cliente.get("/gestoras", params={"pagina": 0})

        self.assertEqual(respuesta.status_code, 422)
        cuerpo = respuesta.json()
        self.assertEqual(cuerpo["codigo"], "PARAMETRO_NO_VALIDO")
        self.assertEqual(
            cuerpo["correlation_id"], respuesta.headers["X-Correlation-Id"]
        )
        self.assertEqual(cuerpo["detalles"][0]["campo"], "query.pagina")

    def test_correlation_id_invalido_genera_uno_nuevo_y_devuelve_422(self) -> None:
        correlation_id_invalido = "a" * 129

        respuesta = self.cliente.get(
            "/health",
            headers={"X-Correlation-Id": correlation_id_invalido},
        )

        self.assertEqual(respuesta.status_code, 422)
        correlation_id_generado = respuesta.headers["X-Correlation-Id"]
        UUID(correlation_id_generado)
        self.assertEqual(respuesta.json()["correlation_id"], correlation_id_generado)

    def test_openapi_contiene_las_operaciones_acordadas(self) -> None:
        esquema = self.cliente.get("/openapi.json").json()
        operaciones = {
            ruta: next(iter(definicion.values()))["operationId"]
            for ruta, definicion in esquema["paths"].items()
        }

        self.assertEqual(
            operaciones,
            {
                "/health": "obtenerEstado",
                "/gestoras": "listarGestoras",
                "/fondos": "listarFondos",
                "/fondos/{isin}": "obtenerFondo",
                "/kids": "listarKids",
            },
        )

        for ruta in operaciones:
            operacion = next(iter(esquema["paths"][ruta].values()))
            self.assertTrue({"422", "500"}.issubset(operacion["responses"]))


class TestErroresTecnicosFastAPI(unittest.TestCase):
    def test_error_repositorio_devuelve_500_sin_exponer_el_detalle(self) -> None:
        servicio = create_autospec(ServicioFondos, instance=True)
        servicio.listar_gestoras.side_effect = ErrorRepositorio(
            "Credenciales de base de datos incorrectas."
        )

        with self.assertLogs("api.http.errors", level="ERROR") as logs:
            with TestClient(
                crear_aplicacion(servicio),
                raise_server_exceptions=False,
            ) as cliente:
                respuesta = cliente.get("/gestoras")

        self.assertEqual(respuesta.status_code, 500)
        self.assertEqual(respuesta.json()["codigo"], "ERROR_INTERNO")
        self.assertNotIn("Credenciales", respuesta.text)
        self.assertIn("Error al consultar el repositorio", logs.output[0])


if __name__ == "__main__":
    unittest.main()
