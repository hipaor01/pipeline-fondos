"""Etapa PDF -> Markdown con PDF reales de Bestinver y S3 en memoria."""

import pymupdf

from procesamiento import markdown
from procesamiento.almacen import AlmacenS3
from tests.procesamiento.conftest import BUCKET, FIXTURES, evento_sqs

CLAVE_KID = "raw/bestinver/20261119/bestinfond_datos_fundamentales.pdf"
CLAVE_MD = "processed/markdown/bestinver/20261119/bestinfond_datos_fundamentales.md"


def _subir_pdf(s3, clave, contenido, **metadatos):
    base = {
        "gestora": "bestinver",
        "tipo_documento": "datos_fundamentales",
        "url_origen": "https://www.bestinver.es/x.pdf",
        "correlation_id": "corr-1",
    }
    s3.put_object(
        Bucket=BUCKET, Key=clave, Body=contenido, Metadata={**base, **metadatos}
    )


def test_convierte_kid_y_conserva_trazabilidad(s3):
    _subir_pdf(
        s3, CLAVE_KID, (FIXTURES / "bestinfond_datos_fundamentales.pdf").read_bytes()
    )
    respuesta = markdown.handler(evento_sqs(CLAVE_KID), almacen=AlmacenS3(s3))

    assert respuesta == {"batchItemFailures": []}
    objeto = s3.get_object(Bucket=BUCKET, Key=CLAVE_MD)
    texto = objeto["Body"].read().decode()
    assert "ES0114673033" in texto and "clase de riesgo 4" in texto
    meta = objeto["Metadata"]
    assert meta["pdf-key"] == CLAVE_KID and meta["pdf-version-id"] == "v1"
    assert len(meta["pdf-sha256"]) == 64
    assert (
        meta["correlation-id"] == "corr-1"
        and meta["tipo-documento"] == "datos_fundamentales"
    )
    assert meta["conversor"].startswith("pymupdf4llm-") and meta["modo-ocr"] == "nunca"


def test_reprocesar_el_mismo_pdf_no_reescribe(s3):
    _subir_pdf(
        s3, CLAVE_KID, (FIXTURES / "bestinfond_datos_fundamentales.pdf").read_bytes()
    )
    almacen = AlmacenS3(s3)
    assert (
        markdown.procesar(
            markdown.eventos.ObjetoS3(BUCKET, CLAVE_KID, None), almacen, "nunca"
        )
        == "CONVERTIDO"
    )
    assert (
        markdown.procesar(
            markdown.eventos.ObjetoS3(BUCKET, CLAVE_KID, None), almacen, "nunca"
        )
        == "OMITIDO"
    )
    assert s3.escrituras.count(CLAVE_MD) == 1


def test_pdf_sin_texto_queda_rechazado_y_no_se_reintenta(s3):
    documento = pymupdf.open()
    documento.new_page()
    clave = "raw/bestinver/20261119/escaneado_datos_fundamentales.pdf"
    _subir_pdf(s3, clave, documento.tobytes())

    respuesta = markdown.handler(evento_sqs(clave), almacen=AlmacenS3(s3))

    assert respuesta == {"batchItemFailures": []}
    auditoria = s3.json(
        "processed/structured/bestinver/20261119/escaneado_datos_fundamentales.json"
    )
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
