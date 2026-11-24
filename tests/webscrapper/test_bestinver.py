"""Pruebas de descubrimiento sin peticiones a la web."""

import json
import re
from datetime import datetime, timezone
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
    ejecutar,
    main,
    obtener_fondos,
)
from webscrapper.ingesta import descargar

FIXTURES = Path(__file__).parent / "fixtures"


def respuesta(contenido: str | bytes) -> Mock:
    return Mock(content=contenido.encode() if isinstance(contenido, str) else contenido, encoding="utf-8", raise_for_status=Mock())


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
    assert documentos[0].nombre_fondo == "Bestinfond España"
    assert session.get.call_count == 2
    assert session.get.call_args_list[0].args[0] == BASE_URL
    assert "usando respaldo" not in capsys.readouterr().out


def test_listado_solo_acepta_fondos_del_origen_y_normaliza_url() -> None:
    session = Mock()
    session.get.return_value = respuesta(
        '<footer><a href="https://otro.test/fondos-de-inversion/falso/">Falso</a>'
        '<a href="http://www.bestinver.es/fondos-de-inversion/inseguro/">Inseguro</a>'
        '<a href="/fondos-de-inversion/uno?ref=x">Uno</a>'
        '<a href="/fondos-de-inversion/uno/#seccion">Uno repetido</a></footer>'
    )
    assert obtener_fondos(session) == [("Uno", "https://www.bestinver.es/fondos-de-inversion/uno/")]


def test_fallbacks_y_documento_ausente() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<footer><a href="/fondos-de-inversion/uno/">Uno</a></footer>'),
        respuesta('<main><a href="/kid.pdf">Datos fundamentales</a></main>'),
    ]

    documentos = ScraperBestinver(session, delay=0).descubrir()

    assert [d.tipo for d in documentos] == ["kid"]


def test_respaldo_si_lista_principal_existe_pero_no_contiene_fondos() -> None:
    session = Mock()
    principal = (FIXTURES / "listado.html").read_text()
    principal = principal.replace(
        '<a href="/fondos-de-inversion/bestinfond/">Bestinfond España</a>',
        '<a href="/otra-ruta/">Enlace no válido</a>',
    ).replace('<li><a href="/fondos-de-inversion/bestinfond/">Bestinfond repetido</a></li>', '')
    principal = principal.replace('</footer>', '<a href="/fondos-de-inversion/uno/">Uno</a></footer>')
    session.get.side_effect = [respuesta(principal), respuesta('<main><a href="/kid.pdf">Datos fundamentales</a></main>')]
    assert [d.slug for d in ScraperBestinver(session, delay=0).descubrir()] == ["uno"]


def test_respaldo_completa_kid_fuera_del_bloque_principal() -> None:
    session = Mock()
    fondo = (FIXTURES / "fondo.html").read_text().replace(
        '<li><a href="/bestinfond-kid.pdf">Datos fundamentales</a></li>', ''
    ).replace('</main>', '<a href="/nuevo-kid.pdf">Datos fundamentales</a></main>')
    session.get.side_effect = [respuesta((FIXTURES / "listado.html").read_text()), respuesta(fondo)]
    scraper = ScraperBestinver(session, delay=0)
    docs = scraper.descubrir()
    assert {d.tipo: d.url for d in docs} == {
        "kid": "https://www.bestinver.es/nuevo-kid.pdf",
        "ficha_fondo": "https://www.bestinver.es/bestinfond-ficha.pdf",
    }
    assert not scraper.fallos


def test_respaldo_si_bloque_principal_de_documentos_esta_vacio() -> None:
    session = Mock()
    fondo = (FIXTURES / "fondo.html").read_text()
    fondo = fondo.replace('<li><a href="/bestinfond-kid.pdf">Datos fundamentales</a></li>', '')
    fondo = fondo.replace('<li><a href="/bestinfond-ficha.pdf">Ficha del fondo</a></li>', '')
    fondo = fondo.replace('</main>', '<a href="/kid.pdf">Datos fundamentales</a></main>')
    session.get.side_effect = [respuesta((FIXTURES / "listado.html").read_text()), respuesta(fondo)]
    scraper = ScraperBestinver(session, delay=0)
    assert [d.tipo for d in scraper.descubrir()] == ["kid"]
    assert not scraper.fallos


def test_solo_fichas_no_se_considera_captura_completa() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<footer><a href="/fondos-de-inversion/uno/">Uno</a></footer>'),
        respuesta('<main><a href="/ficha.pdf">Ficha del fondo</a></main>'),
        respuesta(pdf_valido()),
    ]
    s3 = Mock()
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.put_object.return_value = {"VersionId": "v1"}
    with (
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
    ):
        resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))
    assert resultado.estado == "parcial"
    assert [subida.documento.tipo for subida in resultado.subidos] == ["ficha_fondo"]
    assert any(fallo.mensaje == "No se encontraron documentos KID" for fallo in resultado.fallos)
    assert json.loads(s3.put_object.call_args_list[-1].kwargs["Body"])["estado"] == "parcial"


def test_html_vacio_en_fondo_no_impide_otros_y_deja_manifiesto() -> None:
    session, s3 = Mock(), Mock()
    session.get.side_effect = [
        respuesta('<footer><a href="/fondos-de-inversion/uno/">Uno</a><a href="/fondos-de-inversion/dos/">Dos</a></footer>'),
        respuesta(''),
        respuesta('<main><a href="/kid.pdf">Datos fundamentales</a></main>'),
        respuesta(pdf_valido()),
    ]
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.put_object.return_value = {"VersionId": "v1"}
    with (
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
    ):
        resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))
    assert resultado.estado == "parcial"
    assert [x.documento.slug for x in resultado.subidos] == ["dos"]
    assert [(x.etapa, x.fondo) for x in resultado.fallos] == [("pagina", "Uno")]
    manifiesto = json.loads(s3.put_object.call_args_list[-1].kwargs["Body"])
    assert manifiesto["estado"] == "parcial" and manifiesto["fallos"][0]["etapa"] == "pagina"


def test_html_vacio_en_listado_deja_manifiesto_fallido() -> None:
    session, s3 = Mock(), Mock()
    session.get.return_value = respuesta('')
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.put_object.return_value = {"VersionId": "v1"}
    with (
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
    ):
        resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))
    assert resultado.estado == "fallida" and resultado.fallos[0].etapa == "listado"
    assert json.loads(s3.put_object.call_args.kwargs["Body"])["estado"] == "fallida"


def test_kid_ausente_en_un_fondo_no_se_oculta_por_los_demas() -> None:
    session, s3 = Mock(), Mock()
    session.get.side_effect = [
        respuesta('<footer><a href="/fondos-de-inversion/uno/">Uno</a><a href="/fondos-de-inversion/dos/">Dos</a></footer>'),
        respuesta('<main><a href="/kid.pdf">Datos fundamentales</a></main>'),
        respuesta('<main><a href="/ficha.pdf">Ficha del fondo</a></main>'),
        respuesta(pdf_valido()), respuesta(pdf_valido()),
    ]
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.put_object.return_value = {"VersionId": "v1"}
    with (
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
    ):
        resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))
    assert resultado.estado == "parcial"
    assert [(f.etapa, f.fondo) for f in resultado.fallos] == [("kid_ausente", "Dos")]
    manifiesto = json.loads(s3.put_object.call_args_list[-1].kwargs["Body"])
    assert manifiesto["estado"] == "parcial" and manifiesto["fallos"][0]["tipo"] == "kid"


def test_enlaces_ambiguos_no_se_eligen_y_otros_tipos_se_conservan() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<footer><a href="/fondos-de-inversion/uno/">Uno</a></footer>'),
        respuesta('<main><a href="/a.pdf">Datos fundamentales</a><a href="/b.pdf">Datos fundamentales</a><a href="/ficha.pdf">Ficha del fondo</a></main>'),
    ]
    scraper = ScraperBestinver(session, delay=0)
    docs = scraper.descubrir()
    assert [(d.tipo, d.url) for d in docs] == [("ficha_fondo", "https://www.bestinver.es/ficha.pdf")]
    assert any(f.etapa == "documentos_ambiguos" and f.tipo == "kid" for f in scraper.fallos)


def test_enlaces_repetidos_del_mismo_documento_no_son_ambiguos() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<footer><a href="/fondos-de-inversion/uno/">Uno</a></footer>'),
        respuesta('<main><a href="/a.pdf">Datos fundamentales</a><a href="/a.pdf">Datos fundamentales</a></main>'),
    ]
    scraper = ScraperBestinver(session, delay=0)
    assert [d.tipo for d in scraper.descubrir()] == ["kid"]
    assert not scraper.fallos


def test_categoria_descubre_fondos_hijos_y_evitan_enlaces_externos() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<footer><a href="/fondos-de-inversion/otros/">Otros</a></footer>'),
        respuesta('<main><a href="/fondos-de-inversion/otros/uno/">Uno</a><a href="/fondos-de-inversion/otros/uno/">Ver producto</a><a href="https://otro.test/fondos-de-inversion/otros/falso/">Falso</a><a href="/fondos-de-inversion/otros/folleto.pdf">Folleto</a></main>'),
        respuesta('<main><a href="/kid.pdf">Datos fundamentales</a></main>'),
    ]
    scraper = ScraperBestinver(session, delay=0)
    assert [(d.slug, d.tipo) for d in scraper.descubrir()] == [("uno", "kid")]
    assert not scraper.fallos
    assert len(session.get.call_args_list) == 3


def test_pagina_sin_documentos_ni_productos_sigue_siendo_fallo() -> None:
    session = Mock()
    session.get.side_effect = [
        respuesta('<footer><a href="/fondos-de-inversion/uno/">Uno</a></footer>'),
        respuesta('<main><h1>Uno</h1></main>'),
    ]
    scraper = ScraperBestinver(session, delay=0)
    assert scraper.descubrir() == []
    assert any(f.etapa == "kid_ausente" for f in scraper.fallos)


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
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
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
    for contenido in ("", "<html>error</html>", "%PDF-1.4\nincompleto", b"%PDF-1.4\nstartxref\n999999999999999999999999999999\n%%EOF"):
        session = Mock()
        session.get.return_value = respuesta(contenido)
        try:
            descargar(session, "https://ejemplo.test/kid.pdf")
        except ValueError:
            pass
        else:
            raise AssertionError("Se aceptó una respuesta que no es un PDF")


def test_acepta_pdf_con_tabla_de_referencias_recuperable() -> None:
    contenido = re.sub(rb"startxref\n\d+\n%%EOF", b"startxref\n1\n%%EOF", pdf_valido())
    session = Mock()
    session.get.return_value = respuesta(contenido)
    assert descargar(session, "https://ejemplo.test/kid.pdf") == contenido


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
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
        patch.object(ScraperBestinver, "descubrir", return_value=documentos),
    ):
        main()

    assert len([call for call in s3.put_object.call_args_list if call.kwargs["Key"].endswith(".pdf")]) == 1
    assert "documento duplicado en la ejecución" in capsys.readouterr().out


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
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
    ):
        resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))

    assert resultado.estado == "parcial"
    assert [subida.documento.tipo for subida in resultado.subidos] == ["kid"]
    assert [(fallo.etapa, fallo.tipo) for fallo in resultado.fallos] == [("descarga", "ficha_fondo")]
    manifiesto = json.loads(s3.put_object.call_args_list[-1].kwargs["Body"])
    assert manifiesto["estado"] == "parcial"
    assert manifiesto["fallos"][0]["etapa"] == "descarga"


def test_pdf_con_indice_fuera_de_rango_no_impide_otros_documentos() -> None:
    session, s3 = Mock(), Mock()
    session.get.side_effect = [
        respuesta((FIXTURES / "listado.html").read_text()),
        respuesta((FIXTURES / "fondo.html").read_text()),
        respuesta(b"%PDF-1.4\nstartxref\n999999999999999999999999999999\n%%EOF"),
        respuesta(pdf_valido()),
    ]
    s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
    s3.put_object.return_value = {"VersionId": "v1"}
    with (
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
    ):
        resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))
    assert resultado.estado == "parcial"
    assert [x.documento.tipo for x in resultado.subidos] == ["ficha_fondo"]
    assert [(x.etapa, x.tipo) for x in resultado.fallos] == [("descarga", "kid")]
    manifiesto = json.loads(s3.put_object.call_args_list[-1].kwargs["Body"])
    assert manifiesto["estado"] == "parcial" and manifiesto["fallos"][0]["etapa"] == "descarga"


def test_error_de_listado_o_bucket_produce_estado_fallido() -> None:
    for etapa in ("bucket", "listado"):
        s3, session = Mock(), Mock()
        s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
        if etapa == "bucket":
            s3.head_bucket.side_effect = ClientError({"Error": {"Code": "403", "Message": "denegado"}}, "HeadBucket")
        else:
            session.get.side_effect = requests.Timeout("tiempo agotado")
        with (
            patch("webscrapper.ingesta.requests.Session", return_value=session),
            patch("webscrapper.ingesta.boto3.client", return_value=s3),
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
        patch("webscrapper.ingesta.requests.Session", return_value=session),
        patch("webscrapper.ingesta.boto3.client", return_value=s3),
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
            patch("webscrapper.ingesta.requests.Session", return_value=session),
            patch("webscrapper.ingesta.boto3.client", return_value=s3),
            patch.object(ScraperBestinver, "descubrir", return_value=documentos),
        ):
            resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))
        assert resultado.estado == "parcial"
        assert resultado.fallos[-1].etapa == ("version_s3" if falta_version else "manifiesto_resultado_incierto")


def test_bucket_sin_versionado_no_recibe_subidas() -> None:
    s3 = Mock()
    s3.get_bucket_versioning.return_value = {"Status": "Suspended"}
    with patch("webscrapper.ingesta.boto3.client", return_value=s3):
        resultado = ejecutar(SimpleNamespace(fecha="20261122", prefijo="bestinver", bucket="prueba", delay=0))
    assert resultado.estado == "fallida"
    assert resultado.fallos[0].etapa == "versionado"
    s3.put_object.assert_not_called()


def test_fecha_de_cada_descarga_cruza_medianoche_y_override() -> None:
    for fecha, esperadas in [(None, ["20261122", "20261123"]), ("20260101", ["20260101", "20260101"])]:
        session, s3 = Mock(), Mock()
        session.get.return_value = respuesta(pdf_valido())
        s3.get_bucket_versioning.return_value = {"Status": "Enabled"}
        s3.put_object.return_value = {"VersionId": "v1"}
        documentos = [Documento("bestinver", str(i), "kid", "https://ejemplo.test/kid.pdf", str(i)) for i in range(2)]
        tiempos = [datetime(2026, 11, 22, 22, 59, tzinfo=timezone.utc), datetime(2026, 11, 22, 22, 59, tzinfo=timezone.utc), datetime(2026, 11, 22, 23, 1, tzinfo=timezone.utc), datetime(2026, 11, 22, 23, 2, tzinfo=timezone.utc)]
        with (patch("webscrapper.ingesta.requests.Session", return_value=session), patch("webscrapper.ingesta.boto3.client", return_value=s3), patch.object(ScraperBestinver, "descubrir", return_value=documentos), patch("webscrapper.ingesta.datetime") as reloj):
            reloj.now.side_effect = tiempos
            ejecutar(SimpleNamespace(fecha=fecha, prefijo="bestinver", bucket="prueba", delay=0))
        claves = [c.kwargs["Key"] for c in s3.put_object.call_args_list]
        assert claves[:2] == [f"raw/bestinver/{dia}/{i}_kid.pdf" for i, dia in enumerate(esperadas)]
        assert claves[2].startswith(f"manifests/bestinver/{fecha or '20261122'}/")
