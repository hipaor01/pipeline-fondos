"""Pruebas de selección y configuración del repositorio de la aplicación."""

import unittest
from unittest.mock import create_autospec, patch

from api.app import (
    ErrorConfiguracionRepositorio,
    crear_aplicacion,
    crear_repositorio_desde_entorno,
)
from api.repositories.aurora import RepositorioFondosAurora
from api.repositories.memory import RepositorioFondosEnMemoria
from api.services.fondos import ServicioFondos


class TestConfiguracionRepositorio(unittest.TestCase):
    def test_utiliza_memoria_por_defecto(self) -> None:
        repositorio = crear_repositorio_desde_entorno({})

        self.assertIsInstance(repositorio, RepositorioFondosEnMemoria)

    def test_construye_aurora_con_la_configuracion_completa(self) -> None:
        entorno = {
            "REPOSITORIO_FONDOS": " AURORA ",
            "DB_CLUSTER_ARN": "arn:aws:rds:eu-west-3:123456789012:cluster:fondos",
            "DB_SECRET_ARN": (
                "arn:aws:secretsmanager:eu-west-3:123456789012:secret:fondos"
            ),
            "DB_NAME": "fondos",
        }
        ejecutor = object()

        with patch("api.app.EjecutorDataAPI", return_value=ejecutor) as constructor:
            repositorio = crear_repositorio_desde_entorno(entorno)

        self.assertIsInstance(repositorio, RepositorioFondosAurora)
        constructor.assert_called_once_with(
            cluster_arn=entorno["DB_CLUSTER_ARN"],
            secret_arn=entorno["DB_SECRET_ARN"],
            base_datos=entorno["DB_NAME"],
        )

    def test_rechaza_una_fuente_no_soportada(self) -> None:
        with self.assertRaisesRegex(
            ErrorConfiguracionRepositorio,
            "REPOSITORIO_FONDOS",
        ):
            crear_repositorio_desde_entorno({"REPOSITORIO_FONDOS": "sqlite"})

    def test_rechaza_una_configuracion_aurora_incompleta(self) -> None:
        entorno = {
            "REPOSITORIO_FONDOS": "aurora",
            "DB_CLUSTER_ARN": "arn:cluster",
            "DB_SECRET_ARN": " ",
        }

        with self.assertRaises(ErrorConfiguracionRepositorio) as contexto:
            crear_repositorio_desde_entorno(entorno)

        self.assertIn("DB_SECRET_ARN", str(contexto.exception))
        self.assertIn("DB_NAME", str(contexto.exception))
        self.assertNotIn("arn:cluster", str(contexto.exception))

    def test_el_servicio_inyectado_tiene_prioridad_sobre_el_entorno(self) -> None:
        servicio = create_autospec(ServicioFondos, instance=True)

        with patch("api.app.crear_repositorio_desde_entorno") as crear_repositorio:
            aplicacion = crear_aplicacion(
                servicio,
                entorno={"REPOSITORIO_FONDOS": "no-soportado"},
            )

        self.assertIs(aplicacion.state.servicio_fondos, servicio)
        crear_repositorio.assert_not_called()


if __name__ == "__main__":
    unittest.main()
