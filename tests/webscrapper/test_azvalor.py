"""Pruebas de Azvalor con HTML representativo y AWS simulado."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from tests.webscrapper.test_bestinver import pdf_valido, respuesta
from webscrapper.descargar_kids_azvalor import ScraperAzvalor, main, obtener_documentos

FIXTURES = Path(__file__).parent / "fixtures"


def contenido(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


def test_descubre_fondo_y_clases_distintas_con_documentos_y_isin(capsys) -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta(contenido("azvalor_listado.html")),
        respuesta(contenido("azvalor_fondo.html")),
        respuesta(contenido("azvalor_sicav.html")),
        respuesta(
            contenido("azvalor_sicav.html").replace("LU1333146287", "LU1333148903")
        ),
    ]
    scraper = ScraperAzvalor(session, delay=0)
    docs = scraper.descubrir()
    assert len(docs) == 6
    assert [d.isin for d in docs if d.tipo == "kid"] == [
        "ES0112611001",
        "LU1333146287",
        "LU1333148903",
    ]
    assert [d.nombre_clase for d in docs if d.tipo == "kid"] == [
        None,
        "Clase I",
        "Clase R",
    ]
    assert len({d.slug for d in docs if d.tipo == "kid"}) == 3
    assert docs[3].url == docs[5].url
    assert not scraper.fallos and not scraper.ausentes
    assert "usando respaldo" not in capsys.readouterr().out


def test_respaldo_deduplica_enlaces_e_identifica_ficha_ausente() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<a href="/fondos-de-inversion/ejemplo/">Ejemplo</a>'),
        respuesta(
            '<a href="/dfp.pdf">Folleto simplificado (DFP)</a><a href="/dfp.pdf">Folleto simplificado (DFP)</a>'
        ),
    ]
    scraper = ScraperAzvalor(session, delay=0)
    docs = scraper.descubrir()
    assert [(d.slug, d.tipo) for d in docs] == [("ejemplo", "kid")]
    assert [(a.tipo, a.etapa) for a in scraper.ausentes] == [("ficha_fondo", "ausente")]
    assert not scraper.fallos


def test_kid_ausente_de_un_producto_es_un_fallo() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<a href="/fondos-de-inversion/uno/">Uno</a><a href="/fondos-de-inversion/dos/">Dos</a>'),
        respuesta('<a href="/kid.pdf">Folleto simplificado (DFP)</a>'),
        respuesta('<a href="/ficha.pdf">Ficha del producto</a>'),
    ]
    scraper = ScraperAzvalor(session, delay=0)
    docs = scraper.descubrir()
    assert [(d.slug, d.tipo) for d in docs] == [("uno", "kid"), ("dos", "ficha_fondo")]
    assert [(f.etapa, f.fondo) for f in scraper.fallos] == [("kid_ausente", "Dos")]


def test_dos_kid_diferentes_no_se_eligen_arbitrariamente() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<a href="/fondos-de-inversion/ejemplo/">Ejemplo</a>'),
        respuesta(
            '<a href="/a.pdf">Folleto simplificado (DFP)</a><a href="/b.pdf">Folleto simplificado (DFP)</a>'
        ),
    ]
    scraper = ScraperAzvalor(session, delay=0)
    assert scraper.descubrir() == []
    assert any(
        f.etapa == "documentos_ambiguos" and f.tipo == "kid" for f in scraper.fallos
    )


def test_error_de_una_pagina_no_impide_procesar_otra() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta(contenido("azvalor_listado.html")),
        requests.Timeout("timeout"),
        respuesta(contenido("azvalor_sicav.html")),
        respuesta(contenido("azvalor_sicav.html")),
    ]
    scraper = ScraperAzvalor(session, delay=0)
    assert len(scraper.descubrir()) == 4
    assert [(f.etapa, f.fondo) for f in scraper.fallos] == [
        ("pagina", "Azvalor Internacional FI")
    ]


def test_no_considera_un_folleto_completo_un_kid() -> None:
    session = Mock()
    session.get.return_value = respuesta('<a href="/folleto.pdf">Folleto completo</a>')
    docs, isin = obtener_documentos(
        session, "https://www.azvalor.com/fondos-de-inversion/ejemplo/"
    )
    assert docs == {} and isin is None


def test_usa_respaldo_si_solo_el_kid_esta_fuera_del_bloque_principal() -> None:
    session = Mock()
    html = (
        contenido("azvalor_fondo.html")
        .replace(
            '<a href="/wp-content/uploads/dfp.pdf">Folleto simplificado (DFP)</a>',
            "",
        )
        .replace(
            "</body>", '<a href="/nuevo-dfp.pdf">Folleto simplificado (DFP)</a></body>'
        )
    )
    session.get.return_value = respuesta(html)
    docs, _ = obtener_documentos(
        session, "https://www.azvalor.com/fondos-de-inversion/ejemplo/"
    )
    assert docs["kid"] == {"https://www.azvalor.com/nuevo-dfp.pdf"}
    assert docs["ficha_fondo"] == {
        "https://www.azvalor.com/wp-content/uploads/ficha.pdf"
    }


def test_cli_escribe_kid_ficha_y_manifiesto_en_azvalor() -> None:
    session, s3 = Mock(), Mock()
    session.get.side_effect = [
        respuesta('<a href="/fondos-de-inversion/ejemplo/">Ejemplo</a>'),
        respuesta(contenido("azvalor_fondo.html")),
        respuesta(pdf_valido()),
        respuesta(pdf_valido()),
    ]
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.put_object.return_value = {"VersionId": "v1"}
    with (
        patch(
            "sys.argv",
            [
                "scraper",
                "--bucket",
                "prueba",
                "--fecha",
                "20261123",
                "--delay",
                "0",
                "--correlation-id",
                "test-azvalor",
            ],
        ),
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
    ):
        assert main() == 0
    calls = s3.put_object.call_args_list
    assert [c.kwargs["Key"] for c in calls[:2]] == [
        "raw/azvalor/20261123/ejemplo_kid.pdf",
        "raw/azvalor/20261123/ejemplo_ficha_fondo.pdf",
    ]
    assert calls[0].kwargs["Metadata"]["gestora"] == "azvalor"
    assert calls[2].kwargs["Key"].startswith("manifests/azvalor/")
    manifest = json.loads(calls[2].kwargs["Body"])
    assert manifest["gestora"] == "azvalor" and manifest["estado"] == "completa"
    assert manifest["subidos"][0]["documento"]["isin"] == "ES0112611001"
