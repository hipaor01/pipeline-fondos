"""Pruebas de los modelos públicos de error."""

import unittest

from pydantic import ValidationError

from api.models.error import DetalleError, Error


class TestDetalleError(unittest.TestCase):
    def test_acepta_un_detalle_valido(self) -> None:
        detalle = DetalleError(
            campo="query.pagina",
            mensaje="Debe ser mayor o igual que 1.",
        )

        self.assertEqual(detalle.campo, "query.pagina")

    def test_rechaza_campos_adicionales(self) -> None:
        with self.assertRaises(ValidationError):
            DetalleError(campo="query.pagina", mensaje="No válido", valor=0)


class TestError(unittest.TestCase):
    def test_acepta_y_convierte_una_respuesta_valida(self) -> None:
        error = Error(
            codigo="PARAMETRO_NO_VALIDO",
            mensaje="Uno o varios parámetros no son válidos.",
            correlation_id="8f142b1c-c07b-4b73-9597-45ec0ee03716",
            detalles=[
                {
                    "campo": "query.pagina",
                    "mensaje": "Debe ser mayor o igual que 1.",
                }
            ],
        )

        self.assertIsInstance(error.detalles[0], DetalleError)

    def test_usa_una_lista_vacia_si_no_hay_detalles(self) -> None:
        error = Error(
            codigo="FONDO_NO_ENCONTRADO",
            mensaje="El fondo solicitado no existe.",
            correlation_id="correlation-id-de-prueba",
        )

        self.assertEqual(error.detalles, [])
        self.assertNotIn("detalles", Error.model_json_schema()["required"])

    def test_no_permite_detalles_nulos(self) -> None:
        with self.assertRaises(ValidationError):
            Error(
                codigo="ERROR_INTERNO",
                mensaje="Error técnico.",
                correlation_id="correlation-id-de-prueba",
                detalles=None,
            )

    def test_rechaza_codigos_de_error_invalidos(self) -> None:
        for codigo in ("parametro_no_valido", "1_ERROR", "ERROR-CON-GUION"):
            with self.subTest(codigo=codigo), self.assertRaises(ValidationError):
                Error(
                    codigo=codigo,
                    mensaje="Error de prueba.",
                    correlation_id="correlation-id-de-prueba",
                )

    def test_rechaza_correlation_id_vacio_o_demasiado_largo(self) -> None:
        for correlation_id in ("", "a" * 129):
            with (
                self.subTest(correlation_id=correlation_id),
                self.assertRaises(ValidationError),
            ):
                Error(
                    codigo="ERROR_INTERNO",
                    mensaje="Error técnico.",
                    correlation_id=correlation_id,
                )


if __name__ == "__main__":
    unittest.main()
