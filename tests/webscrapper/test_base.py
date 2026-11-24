"""Ejemplos del contrato de descubrimiento para las gestoras previstas."""

import argparse

import pytest

from webscrapper.base import Documento, ScraperGestora
from webscrapper.ingesta import fecha_valida


def test_el_contrato_representa_fondos_y_clases() -> None:
    documentos = [
        Documento("bestinver", "bestinfond", "kid", "https://ejemplo.test/a.pdf", "Bestinfond"),
        Documento("azvalor", "internacional", "ficha_fondo", "https://ejemplo.test/b.pdf", "Internacional"),
        Documento("cobas-am", "seleccion-clase-a", "kid", "https://ejemplo.test/c.pdf", "Selección", "Clase A", "ES0000000001"),
    ]

    class ScraperEjemplo:
        def descubrir(self) -> list[Documento]:
            return documentos

    scraper: ScraperGestora = ScraperEjemplo()
    assert scraper.descubrir()[2].nombre_clase == "Clase A"
    assert scraper.descubrir()[2].isin == "ES0000000001"
    assert {documento.gestora for documento in scraper.descubrir()} == {
        "bestinver", "azvalor", "cobas-am"
    }


@pytest.mark.parametrize("valor", ["2026111", "2026011", "202611011", "20261301", "２０２６１１０１"])
def test_fecha_requiere_ocho_digitos_y_dia_valido(valor):
    with pytest.raises(argparse.ArgumentTypeError):
        fecha_valida(valor)


def test_fecha_valida_conserva_formato():
    assert fecha_valida("20261101") == "20261101"
