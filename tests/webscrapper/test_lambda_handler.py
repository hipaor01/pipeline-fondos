"""Pruebas del adaptador Lambda para las tres gestoras."""

from unittest.mock import Mock, patch

import pytest

from webscrapper.base import Documento, Incidencia, ResultadoIngesta, Subida
from webscrapper.ingesta import CORRELATION_ID
from webscrapper.lambda_handler import GESTORAS, handler


@pytest.mark.parametrize("gestora", ["bestinver", "azvalor", "cobas"])
def test_reutiliza_ingesta_y_propaga_correlacion(gestora):
    documento = Documento(
        gestora, "fondo", "kid", "https://ejemplo.test/f.pdf", "Fondo"
    )
    resultado = ResultadoIngesta(
        subidos=[
            Subida(documento, "bucket", "clave", "v1", "a" * 64, "2026-11-24T00:00:00Z")
        ]
    )
    observado = []

    def capturar(*_args):
        observado.append(CORRELATION_ID.get())
        return resultado

    with (
        patch.dict("os.environ", {"GESTORA": gestora, "BUCKET_DOCUMENTOS": "bucket"}),
        patch(
            "webscrapper.lambda_handler.ingesta.ejecutar", side_effect=capturar
        ) as ejecutar,
    ):
        salida = handler({"correlation_id": "ejecucion-1"}, Mock())
    args, scraper, nombre, url = ejecutar.call_args.args
    assert (args.bucket, args.prefijo, nombre, scraper, url) == (
        "bucket",
        gestora,
        gestora,
        *GESTORAS[gestora],
    )
    assert salida == {
        "gestora": gestora,
        "correlation_id": "ejecucion-1",
        "estado": "completa",
        "subidos": 1,
        "ausentes": 0,
        "fallos": 0,
    }
    assert observado == ["ejecucion-1"]
    assert CORRELATION_ID.get() is None


def test_resultado_fallido_no_se_informa_como_exito():
    resultado = ResultadoIngesta(fallos=[Incidencia("listado", "error")])
    with (
        patch.dict("os.environ", {"GESTORA": "cobas", "BUCKET_DOCUMENTOS": "bucket"}),
        patch("webscrapper.lambda_handler.ingesta.ejecutar", return_value=resultado),
    ):
        assert handler({}, Mock())["estado"] == "fallida"


def test_rechaza_identificador_invalido():
    with patch.dict("os.environ", {"GESTORA": "cobas", "BUCKET_DOCUMENTOS": "bucket"}):
        with pytest.raises(ValueError):
            handler({"correlation_id": "x" * 129}, Mock())
