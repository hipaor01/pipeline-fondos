"""Pruebas de descubrimiento sin peticiones a la web."""

from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from pypdf import PdfWriter

from webscrapper.base import Documento
from webscrapper.descargar_kids_bestinver import (
    BASE_URL,
    ScraperBestinver,
    descargar,
    main,
)

FIXTURES = Path(__file__).parent / "fixtures"


def respuesta(contenido: str | bytes) -> Mock:
    return Mock(content=contenido.encode() if isinstance(contenido, str) else contenido, raise_for_status=Mock())


def pdf_valido() -> bytes:
    escritor = PdfWriter()
    escritor.add_blank_page(width=72, height=72)
    contenido = BytesIO()
    escritor.write(contenido)
    return contenido.getvalue()


def test_descubre_fondo_y_documentos_con_selectores_principales(capsys) -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta((FIXTURES / "listado.html").read_text()),
        respuesta((FIXTURES / "fondo.html").read_text()),
    ]
    scraper = ScraperBestinver(session, delay=0)

    documentos = scraper.descubrir()

    assert [(d.slug, d.tipo, d.url) for d in documentos] == [
        ("bestinfond", "kid", "https://www.bestinver.es/bestinfond-kid.pdf"),
        ("bestinfond", "ficha_fondo", "https://www.bestinver.es/bestinfond-ficha.pdf"),
    ]
    assert not scraper.fallos
    assert session.get.call_count == 2
    assert session.get.call_args_list[0].args[0] == BASE_URL
    assert "usando respaldo" not in capsys.readouterr().out


def test_fallbacks_y_documento_ausente() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<footer><a href="/fondos-de-inversion/uno/">Uno</a></footer>'),
        respuesta('<main><a href="/kid.pdf">Datos fundamentales</a></main>'),
    ]

    documentos = ScraperBestinver(session, delay=0).descubrir()

    assert [d.tipo for d in documentos] == ["kid"]


def test_error_de_un_fondo_no_oculta_los_demas() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<footer><a href="/fondos-de-inversion/uno/">Uno</a><a href="/fondos-de-inversion/dos/">Dos</a></footer>'),
        requests.ConnectionError("fallo"),
        respuesta('<main><a href="/kid.pdf">Datos fundamentales</a></main>'),
    ]
    scraper = ScraperBestinver(session, delay=0)

    documentos = scraper.descubrir()

    assert [d.slug for d in documentos] == ["dos"]
    assert scraper.fallos == [("Uno", "página")]


def test_cli_conserva_las_claves_y_metadatos_de_las_subidas(capsys) -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta((FIXTURES / "listado.html").read_text()),
        respuesta((FIXTURES / "fondo.html").read_text()),
        respuesta(pdf_valido()),
        respuesta(pdf_valido()),
    ]
    s3 = Mock()
    with (
        patch("sys.argv", ["scraper", "--fecha", "20261122", "--delay", "0", "--correlation-id", "prueba-1"]),
        patch("webscrapper.descargar_kids_bestinver.requests.Session", return_value=session),
        patch("webscrapper.descargar_kids_bestinver.boto3.client", return_value=s3),
    ):
        main()

    assert [call.kwargs["Key"] for call in s3.put_object.call_args_list] == [
        "bestinver/20261122/bestinfond_datos_fundamentales.pdf",
        "bestinver/20261122/bestinfond_ficha_fondo.pdf",
    ]
    assert s3.put_object.call_args_list[0].kwargs["Metadata"] == {
        "url-origen": "https://www.bestinver.es/bestinfond-kid.pdf",
        "correlation-id": "prueba-1",
    }
    assert all(line.startswith("[prueba-1]") for line in capsys.readouterr().out.splitlines() if line)


def test_rechaza_respuestas_vacias_y_html() -> None:
    for contenido in ("", "<html>error</html>", "%PDF-1.4\nincompleto"):
        session = Mock()
        session.get.return_value = respuesta(contenido)
        try:
            descargar(session, "https://ejemplo.test/kid.pdf")
        except ValueError:
            pass
        else:
            raise AssertionError("Se aceptó una respuesta que no es un PDF")


def test_claves_duplicadas_no_sobrescriben_la_primera_subida(capsys) -> None:
    session = Mock()
    session.get.return_value = respuesta(pdf_valido())
    s3 = Mock()
    documentos = [
        Documento("bestinver", "fondo", "kid", "https://ejemplo.test/a.pdf", "A"),
        Documento("bestinver", "fondo", "kid", "https://ejemplo.test/b.pdf", "B"),
    ]
    with (
        patch("sys.argv", ["scraper", "--fecha", "20261122", "--delay", "0"]),
        patch("webscrapper.descargar_kids_bestinver.requests.Session", return_value=session),
        patch("webscrapper.descargar_kids_bestinver.boto3.client", return_value=s3),
        patch.object(ScraperBestinver, "descubrir", return_value=documentos),
    ):
        main()

    assert s3.put_object.call_count == 1
    assert "clave duplicada" in capsys.readouterr().out
