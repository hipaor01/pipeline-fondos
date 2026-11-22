"""Pruebas de la comprobación de salud del contenedor."""

import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from frontend.healthcheck import (
    TIMEOUT_SEGUNDOS,
    comprobar_salud,
    construir_url_salud,
    main,
)


class TestHealthcheck(unittest.TestCase):
    @patch.dict("os.environ", {}, clear=True)
    def test_construye_la_url_con_el_puerto_por_defecto(self) -> None:
        self.assertEqual(
            construir_url_salud(),
            "http://127.0.0.1:8501/_stcore/health",
        )

    @patch.dict("os.environ", {"STREAMLIT_SERVER_PORT": "9000"}, clear=True)
    def test_respeta_el_puerto_configurado(self) -> None:
        self.assertEqual(
            construir_url_salud(),
            "http://127.0.0.1:9000/_stcore/health",
        )

    @patch("frontend.healthcheck.urllib.request.urlopen")
    def test_acepta_una_respuesta_http_200(self, urlopen: MagicMock) -> None:
        respuesta = MagicMock()
        respuesta.__enter__.return_value.status = 200
        urlopen.return_value = respuesta

        saludable = comprobar_salud("http://127.0.0.1:8501/_stcore/health")

        self.assertTrue(saludable)
        urlopen.assert_called_once_with(
            "http://127.0.0.1:8501/_stcore/health",
            timeout=TIMEOUT_SEGUNDOS,
        )

    @patch("frontend.healthcheck.urllib.request.urlopen")
    def test_devuelve_error_si_no_hay_conexion(self, urlopen: MagicMock) -> None:
        urlopen.side_effect = URLError("conexion rechazada")

        with patch("builtins.print"):
            codigo_salida = main()

        self.assertEqual(codigo_salida, 1)

    @patch.dict("os.environ", {"STREAMLIT_SERVER_PORT": "invalido"}, clear=True)
    def test_devuelve_error_para_un_puerto_invalido(self) -> None:
        with patch("builtins.print"):
            codigo_salida = main()

        self.assertEqual(codigo_salida, 1)


if __name__ == "__main__":
    unittest.main()
