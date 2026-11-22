"""Pruebas del modelo de estado del servicio."""

import unittest

from pydantic import ValidationError

from api.models.system import EstadoSalud, EstadoServicio


class TestEstadoServicio(unittest.TestCase):
    def test_acepta_el_estado_ok(self) -> None:
        estado = EstadoServicio(
            estado="ok",
            servicio="api-fondos",
            version="0.1.0",
        )

        self.assertEqual(estado.estado, EstadoSalud.OK)
        self.assertEqual(estado.model_dump(mode="json")["estado"], "ok")

    def test_rechaza_un_estado_desconocido(self) -> None:
        with self.assertRaises(ValidationError):
            EstadoServicio(
                estado="degraded",
                servicio="api-fondos",
                version="0.1.0",
            )

    def test_requiere_todos_los_campos(self) -> None:
        with self.assertRaises(ValidationError):
            EstadoServicio(estado="ok", servicio="api-fondos")

    def test_rechaza_campos_adicionales(self) -> None:
        with self.assertRaises(ValidationError):
            EstadoServicio(
                estado="ok",
                servicio="api-fondos",
                version="0.1.0",
                base_datos="ok",
            )


if __name__ == "__main__":
    unittest.main()
