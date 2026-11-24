"""Captura de clases de Cobas sin depender de la web ni de AWS."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from tests.webscrapper.test_bestinver import pdf_valido, respuesta
from webscrapper.descargar_kids_cobas import ScraperCobas, main

FIXTURES = Path(__file__).parent / "fixtures"


def contenido(nombre: str) -> str:
    return (FIXTURES / nombre).read_text(encoding="utf-8")


def test_conserva_clases_isin_y_documentos_en_sus_bloques(capsys) -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta(contenido("cobas_listado.html")),
        respuesta(contenido("cobas_clases.html")),
    ]
    scraper = ScraperCobas(session, delay=0)
    docs = scraper.descubrir()
    assert [(d.nombre_clase, d.isin, d.tipo, d.url) for d in docs] == [
        ("Clase A", "ES0124037039", "kid", "https://static.test/a-kid.pdf"),
        ("Clase A", "ES0124037039", "ficha_fondo", "https://static.test/a-ficha.pdf"),
        ("Clase B", "ES0124037021", "kid", "https://static.test/b-kid.pdf"),
        ("Clase B", "ES0124037021", "ficha_fondo", "https://static.test/b-ficha.pdf"),
    ]
    assert [d.slug for d in docs[::2]] == [
        "cobas-seleccion-clase-a",
        "cobas-seleccion-clase-b",
    ]
    assert not scraper.fallos and not scraper.ausentes
    assert "usando respaldo" not in capsys.readouterr().out


def test_respaldo_y_fondo_sin_clase() -> None:
    listado = '<a href="/productos/inversion-libre/renta/">Renta</a>'
    fondo = '<article class="ficha"><div>ES0119207001</div><article class="download-docs"><h3>Documentación fondo - Cobas Renta FI</h3><a href="https://static.test/renta.pdf">PRIIP pdf</a></article></article>'
    session = Mock()
    session.get.side_effect = [respuesta(listado), respuesta(fondo)]
    scraper = ScraperCobas(session, delay=0)
    docs = scraper.descubrir()
    assert [(d.slug, d.nombre_clase, d.isin) for d in docs] == [
        ("renta", None, "ES0119207001")
    ]
    assert [(a.tipo, a.etapa) for a in scraper.ausentes] == [("ficha_fondo", "ausente")]
    assert not scraper.fallos


def test_clase_con_isin_ambiguo_no_se_atribuye_a_otra() -> None:
    pagina = contenido("cobas_clases.html").replace(
        "ES0124037039", "ES0124037039 ES0124037021"
    )
    session = Mock()
    session.get.side_effect = [
        respuesta(contenido("cobas_listado.html")),
        respuesta(pagina),
    ]
    scraper = ScraperCobas(session, delay=0)
    docs = scraper.descubrir()
    assert {d.nombre_clase for d in docs} == {"Clase B"}
    assert [f.etapa for f in scraper.fallos] == ["clase_ambigua"]


def test_kid_ausente_y_multiples_urls_son_fallos() -> None:
    for enlace, esperado in [
        ("", "kid_ausente"),
        ('<a href="https://static.test/otro.pdf">PRIIP pdf</a>', "documentos_ambiguos"),
    ]:
        pagina = contenido("cobas_clases.html")
        original = '<a href="https://static.test/a-kid.pdf">PRIIP <span>pdf</span></a>'
        pagina = pagina.replace(original, enlace if not enlace else original + enlace)
        session = Mock()
        session.get.side_effect = [
            respuesta(contenido("cobas_listado.html")),
            respuesta(pagina),
        ]
        scraper = ScraperCobas(session, delay=0)
        docs = scraper.descubrir()
        assert not any(d.nombre_clase == "Clase A" and d.tipo == "kid" for d in docs)
        assert any(f.etapa == esperado for f in scraper.fallos)


def test_error_de_pagina_no_impide_otros_productos() -> None:
    listado = '<a href="/productos/inversion-libre/uno/">Uno</a><a href="/productos/inversion-libre/dos/">Dos</a>'
    session = Mock()
    session.get.side_effect = [
        respuesta(listado),
        requests.Timeout("agotado"),
        respuesta(contenido("cobas_clases.html")),
    ]
    scraper = ScraperCobas(session, delay=0)
    assert len(scraper.descubrir()) == 4
    assert [f.etapa for f in scraper.fallos] == ["pagina"]


def test_cli_subidas_por_clase_y_manifiesto() -> None:
    session, s3 = Mock(), Mock()
    session.get.side_effect = [
        respuesta(contenido("cobas_listado.html")),
        respuesta(contenido("cobas_clases.html")),
        *[respuesta(pdf_valido()) for _ in range(4)],
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
                "test-cobas",
            ],
        ),
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
    ):
        assert main() == 0
    llamadas = s3.put_object.call_args_list
    assert [c.kwargs["Key"] for c in llamadas[:4]] == [
        "raw/cobas/20261123/cobas-seleccion-clase-a_kid.pdf",
        "raw/cobas/20261123/cobas-seleccion-clase-a_ficha_fondo.pdf",
        "raw/cobas/20261123/cobas-seleccion-clase-b_kid.pdf",
        "raw/cobas/20261123/cobas-seleccion-clase-b_ficha_fondo.pdf",
    ]
    assert llamadas[0].kwargs["Metadata"]["gestora"] == "cobas"
    assert llamadas[4].kwargs["Key"].startswith("manifests/cobas/")
    manifiesto = json.loads(llamadas[4].kwargs["Body"])
    assert manifiesto["gestora"] == "cobas" and manifiesto["estado"] == "completa"
    assert manifiesto["subidos"][0]["documento"]["isin"] == "ES0124037039"


def test_incidencias_identifican_clases_con_url_compartida() -> None:
    pagina = contenido("cobas_clases.html").replace("https://static.test/b-kid.pdf", "https://static.test/a-kid.pdf")
    pagina = pagina.replace('<a href="https://static.test/a-ficha.pdf">Ficha del fondo <span>pdf</span></a>', '')
    session, s3 = Mock(), Mock()
    session.get.side_effect = [respuesta(contenido("cobas_listado.html")), respuesta(pagina), requests.Timeout("agotado"), requests.Timeout("agotado"), respuesta(pdf_valido())]
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.put_object.return_value = {"VersionId": "v1"}
    with (patch("sys.argv", ["scraper", "--fecha", "20261123", "--delay", "0"]), patch("webscrapper.ingesta.requests.Session", return_value=session), patch("webscrapper.ingesta.boto3.client", return_value=s3)):
        main()
    manifiesto = json.loads(s3.put_object.call_args_list[-1].kwargs["Body"])
    assert {(f["nombre_clase"], f["isin"]) for f in manifiesto["fallos"] if f["etapa"] == "descarga"} == {("Clase A", "ES0124037039"), ("Clase B", "ES0124037021")}
    assert any(a["nombre_clase"] == "Clase A" and a["isin"] == "ES0124037039" for a in manifiesto["ausentes"])
