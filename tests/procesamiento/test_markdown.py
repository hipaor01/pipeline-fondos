"""Etapa PDF -> Markdown con PDF reales de Bestinver, S3 en memoria y el contrato C1 v1."""

import hashlib

import pymupdf

from procesamiento import markdown
from procesamiento.almacen import AlmacenS3
from procesamiento.eventos import ObjetoS3
from tests.procesamiento.conftest import BUCKET, FIXTURES, evento_sqs

CLAVE_KID = "raw/bestinver/20261119/bestinfond_kid.pdf"
CLAVE_MD = "processed/markdown/bestinver/20261119/bestinfond_kid.md"
PDF_KID = (FIXTURES / "bestinfond_datos_fundamentales.pdf").read_bytes()


def _json(clave_raw: str) -> str:
    return clave_raw.replace("raw/", "processed/structured/").replace(".pdf", ".json")


def _subir_pdf(s3, clave, contenido, **metadatos):
    """Sube un PDF con los metadatos de C1 v1, como lo hace `webscrapper/ingesta.py`."""
    base = {
        "gestora": "bestinver",
        "tipo-documento": "kid",
        "url-origen": "https://www.bestinver.es/x.pdf",
        "fecha-descarga-utc": "2026-11-19T06:00:00Z",
        "sha256": hashlib.sha256(contenido).hexdigest(),
        "correlation-id": "corr-1",
    }
    finales = {k: v for k, v in {**base, **metadatos}.items() if v is not None}
    respuesta = s3.put_object(
        Bucket=BUCKET, Key=clave, Body=contenido, Metadata=finales
    )
    return respuesta["VersionId"]


def test_convierte_kid_y_conserva_trazabilidad(s3):
    version = _subir_pdf(s3, CLAVE_KID, PDF_KID)
    respuesta = markdown.handler(
        evento_sqs(CLAVE_KID, version_id=version), almacen=AlmacenS3(s3)
    )

    assert respuesta == {"batchItemFailures": []}
    objeto = s3.get_object(Bucket=BUCKET, Key=CLAVE_MD)
    texto = objeto["Body"].read().decode()
    assert "ES0114673033" in texto and "clase de riesgo 4" in texto
    meta = objeto["Metadata"]
    assert meta["pdf-key"] == CLAVE_KID and meta["pdf-version-id"] == version
    assert meta["pdf-sha256"] == hashlib.sha256(PDF_KID).hexdigest()
    assert meta["correlation-id"] == "corr-1" and meta["tipo-documento"] == "kid"
    assert meta["fecha-descarga-utc"] == "2026-11-19T06:00:00Z"
    assert meta["conversor"].startswith("pymupdf4llm-") and meta["modo-ocr"] == "nunca"


def test_lee_la_version_exacta_del_evento(s3):
    """Si la clave cambió después del evento, se procesa la versión del evento, no la última."""
    version_kid = _subir_pdf(s3, CLAVE_KID, PDF_KID)
    _subir_pdf(s3, CLAVE_KID, b"%PDF-1.7 version posterior")

    markdown.procesar(ObjetoS3(BUCKET, CLAVE_KID, version_kid), AlmacenS3(s3), "nunca")

    meta = s3.head_object(Bucket=BUCKET, Key=CLAVE_MD)["Metadata"]
    assert meta["pdf-version-id"] == version_kid
    assert meta["pdf-sha256"] == hashlib.sha256(PDF_KID).hexdigest()


def test_varios_records_en_un_mensaje(s3):
    otra = "raw/bestinver/20261119/bestinver-renta_kid.pdf"
    _subir_pdf(s3, CLAVE_KID, PDF_KID)
    pdf_renta = (FIXTURES / "bestinver-renta_datos_fundamentales.pdf").read_bytes()
    _subir_pdf(s3, otra, pdf_renta)

    respuesta = markdown.handler(evento_sqs(CLAVE_KID, otra), almacen=AlmacenS3(s3))

    assert respuesta == {"batchItemFailures": []}
    assert {
        CLAVE_MD,
        "processed/markdown/bestinver/20261119/bestinver-renta_kid.md",
    } <= set(s3.escrituras)


def test_reprocesar_el_mismo_pdf_no_reescribe(s3):
    _subir_pdf(s3, CLAVE_KID, PDF_KID)
    almacen = AlmacenS3(s3)
    objeto = ObjetoS3(BUCKET, CLAVE_KID, None)
    assert markdown.procesar(objeto, almacen, "nunca") == "CONVERTIDO"
    assert markdown.procesar(objeto, almacen, "nunca") == "OMITIDO"
    assert s3.escrituras.count(CLAVE_MD) == 1


def test_sha256_que_no_coincide_se_rechaza_sin_reintento(s3):
    _subir_pdf(s3, CLAVE_KID, PDF_KID, sha256="0" * 64)

    respuesta = markdown.handler(evento_sqs(CLAVE_KID), almacen=AlmacenS3(s3))

    assert respuesta == {"batchItemFailures": []}
    auditoria = s3.json(_json(CLAVE_KID))
    assert auditoria["estado"] == "REJECTED"
    assert auditoria["motivo"] == "sha256_no_coincide"
    assert CLAVE_MD not in s3.escrituras


def test_faltan_metadatos_c1_se_rechaza(s3):
    _subir_pdf(
        s3, CLAVE_KID, PDF_KID, **{"correlation-id": None, "fecha-descarga-utc": None}
    )

    markdown.handler(evento_sqs(CLAVE_KID), almacen=AlmacenS3(s3))

    auditoria = s3.json(_json(CLAVE_KID))
    assert auditoria["motivo"] == "contrato_c1"
    faltan = {
        v["campo"] for v in auditoria["validaciones"] if v["regla"] == "metadatos_c1"
    }
    assert faltan == {"correlation-id", "fecha-descarga-utc"}


def test_gestora_del_metadato_distinta_de_la_clave_se_rechaza(s3):
    _subir_pdf(s3, CLAVE_KID, PDF_KID, gestora="cobas")
    markdown.handler(evento_sqs(CLAVE_KID), almacen=AlmacenS3(s3))
    assert s3.json(_json(CLAVE_KID))["motivo"] == "contrato_c1"


def test_pdf_sin_texto_queda_rechazado_y_no_se_reintenta(s3):
    documento = pymupdf.open()
    documento.new_page()
    clave = "raw/bestinver/20261119/escaneado_kid.pdf"
    _subir_pdf(s3, clave, documento.tobytes())

    respuesta = markdown.handler(evento_sqs(clave), almacen=AlmacenS3(s3))

    assert respuesta == {"batchItemFailures": []}
    auditoria = s3.json(_json(clave))
    assert auditoria["estado"] == "REJECTED" and auditoria["motivo"] == "markdown_vacio"
    assert not any(k.startswith("processed/markdown/") for k in s3.escrituras)


def test_pdf_corrupto_es_error_tecnico(s3):
    _subir_pdf(s3, CLAVE_KID, b"esto no es un pdf")
    respuesta = markdown.handler(evento_sqs(CLAVE_KID), almacen=AlmacenS3(s3))
    assert respuesta == {"batchItemFailures": [{"itemIdentifier": f"msg-{CLAVE_KID}"}]}


def test_clave_fuera_de_contrato_se_descarta_sin_reintento(s3):
    respuesta = markdown.handler(
        evento_sqs("bestinver/20261119/x.pdf"), almacen=AlmacenS3(s3)
    )
    assert respuesta == {"batchItemFailures": []}
