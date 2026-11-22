"""Pruebas de descubrimiento sin peticiones a la web."""

import json
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from botocore.exceptions import ClientError
from pypdf import PdfWriter

from webscrapper.base import Documento
from webscrapper.descargar_kids_bestinver import (
    BASE_URL,
    ScraperBestinver,
    descargar,
    ejecutar,
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
    assert [(fallo.fondo, fallo.etapa) for fallo in scraper.fallos] == [("Uno", "pagina")]


def test_cli_conserva_las_claves_y_metadatos_de_las_subidas(capsys) -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta((FIXTURES / "listado.html").read_text()),
        respuesta((FIXTURES / "fondo.html").read_text()),
        respuesta(pdf_valido()),
        respuesta(pdf_valido()),
    ]
    s3 = Mock()
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.put_object.return_value = {"VersionId": "v1"}
    with (
        patch("sys.argv", ["scraper", "--fecha", "20261122", "--delay", "0", "--correlation-id", "prueba-1"]),
        patch("webscrapper.descargar_kids_bestinver.requests.Session", return_value=session),
        patch("webscrapper.descargar_kids_bestinver.boto3.client", return_value=s3),
    ):
        main()

    assert [call.kwargs["Key"] for call in s3.put_object.call_args_list[:-1]] == [
        "raw/bestinver/20261122/bestinfond_kid.pdf",
        "raw/bestinver/20261122/bestinfond_ficha_fondo.pdf",
    ]
    subida = s3.put_object.call_args_list[0].kwargs
    metadatos = subida["Metadata"]
    assert metadatos["url-origen"] == "https://www.bestinver.es/bestinfond-kid.pdf"
    assert metadatos["correlation-id"] == "prueba-1"
    assert metadatos["gestora"] == "bestinver"
    assert metadatos["tipo-documento"] == "kid"
    assert metadatos["sha256"] == sha256(subida["Body"]).hexdigest()
    assert metadatos["fecha-descarga-utc"].endswith("Z")
    assert subida["ContentType"] == "application/pdf"
    manifiesto = json.loads(s3.put_object.call_args_list[-1].kwargs["Body"])
    assert manifiesto["estado"] == "completa"
    assert manifiesto["subidos"][0]["version_id"] == "v1"
    assert manifiesto["subidos"][0]["sha256"] == metadatos["sha256"]
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
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.put_object.return_value = {"VersionId": "v1"}
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

    assert len([call for call in s3.put_object.call_args_list if call.kwargs["Key"].endswith(".pdf")]) == 1
    assert "clave S3 duplicada" in capsys.readouterr().out


def test_resultado_parcial_identifica_documento_que_fallo() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta((FIXTURES / "listado.html").read_text()),
        respuesta((FIXTURES / "fondo.html").read_text()),
        respuesta(pdf_valido()),
        requests.Timeout("tiempo agotado"),
    ]
    s3 = Mock()
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.put_object.return_value = {"VersionId": "v1"}
    with (
        patch("webscrapper.descargar_kids_bestinver.requests.Session", return_value=session),
        patch("webscrapper.descargar_kids_bestinver.boto3.client", return_value=s3),
    ):
        resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))

    assert resultado.estado == "parcial"
    assert [subida.documento.tipo for subida in resultado.subidos] == ["kid"]
    assert [(fallo.etapa, fallo.tipo) for fallo in resultado.fallos] == [("descarga", "ficha_fondo")]
    manifiesto = json.loads(s3.put_object.call_args_list[-1].kwargs["Body"])
    assert manifiesto["estado"] == "parcial"
    assert manifiesto["fallos"][0]["etapa"] == "descarga"


def test_error_de_listado_o_bucket_produce_estado_fallido() -> None:
    for etapa in ("bucket", "listado"):
        s3, session = Mock(), Mock()
        s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
        if etapa == "bucket":
            s3.head_bucket.side_effect = ClientError({"Error": {"Code": "403", "Message": "denegado"}}, "HeadBucket")
        else:
            session.get.side_effect = requests.Timeout("tiempo agotado")
        with (
            patch("webscrapper.descargar_kids_bestinver.requests.Session", return_value=session),
            patch("webscrapper.descargar_kids_bestinver.boto3.client", return_value=s3),
        ):
            resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))
        assert resultado.estado == "fallida"
        assert resultado.fallos[0].etapa == etapa


def test_fallo_de_subida_queda_en_manifiesto_como_resultado_incierto() -> None:
    session, s3 = Mock(), Mock()
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    session.get.return_value = respuesta(pdf_valido())
    error = ClientError({"Error": {"Code": "500", "Message": "fallo"}}, "PutObject")
    s3.put_object.side_effect = [error, {}]
    documentos = [Documento("bestinver", "fondo", "kid", "https://ejemplo.test/a.pdf", "Fondo")]
    with (
        patch("webscrapper.descargar_kids_bestinver.requests.Session", return_value=session),
        patch("webscrapper.descargar_kids_bestinver.boto3.client", return_value=s3),
        patch.object(ScraperBestinver, "descubrir", return_value=documentos),
    ):
        resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))

    assert resultado.estado == "fallida"
    manifiesto = json.loads(s3.put_object.call_args_list[-1].kwargs["Body"])
    fallo = manifiesto["fallos"][0]
    assert fallo["etapa"] == "subida_resultado_incierto"
    assert fallo["clave"] == "raw/bestinver/20261122/fondo_kid.pdf"
    assert fallo["sha256"] == sha256(pdf_valido()).hexdigest()


def test_error_del_manifiesto_o_falta_de_version_es_visible() -> None:
    for falta_version in (True, False):
        session, s3 = Mock(), Mock()
        s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
        session.get.return_value = respuesta(pdf_valido())
        error = ClientError({"Error": {"Code": "500", "Message": "fallo"}}, "PutObject")
        s3.put_object.side_effect = [{}, {}] if falta_version else [{"VersionId": "v1"}, error]
        documentos = [Documento("bestinver", "fondo", "kid", "https://ejemplo.test/a.pdf", "Fondo")]
        with (
            patch("webscrapper.descargar_kids_bestinver.requests.Session", return_value=session),
            patch("webscrapper.descargar_kids_bestinver.boto3.client", return_value=s3),
            patch.object(ScraperBestinver, "descubrir", return_value=documentos),
        ):
            resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))
        assert resultado.estado == "parcial"
        assert resultado.fallos[-1].etapa == ("version_s3" if falta_version else "manifiesto_resultado_incierto")


def test_bucket_sin_versionado_no_recibe_subidas() -> None:
    s3 = Mock()
    s3.get_bucket_versioning.return_value = {"Status": "Suspended"}
    with patch("webscrapper.descargar_kids_bestinver.boto3.client", return_value=s3):
        resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))
    assert resultado.estado == "fallida"
    assert resultado.fallos[0].etapa == "versionado"
    s3.put_object.assert_not_called()
