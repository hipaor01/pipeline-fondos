"""Etapa PDF -> Markdown (contrato C2). Handler: `procesamiento.markdown.handler`.

SQS (raw/*.pdf, batch=1) -> esta Lambda -> processed/markdown/...md

- Idempotente: si el .md ya existe para el mismo sha256 del PDF, no se reescribe
  (y por tanto no se vuelve a disparar la extracción).
- Un error técnico (S3, PDF corrupto) se propaga: SQS reintenta y, agotados los
  intentos, el mensaje va a la DLQ.
- Un PDF sin texto (necesitaría OCR, desactivado por defecto) no es un error técnico:
  se deja un JSON REJECTED en processed/structured/ y no se reintenta.
"""

import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from procesamiento import eventos, rutas
from procesamiento.almacen import AlmacenS3, ObjetoLeido
from procesamiento.esquema import Estado, Origen, ResultadoExtraccion, Validacion
from procesamiento.observabilidad import Cronometro, log, metrica_resultado

ETAPA = "pdf_a_markdown"
MIN_CARACTERES = int(os.environ.get("MARKDOWN_MIN_CARACTERES", "200"))
MODOS_OCR = {
    "auto": {"use_ocr": True, "force_ocr": False},
    "nunca": {"use_ocr": False, "force_ocr": False},
    "siempre": {"use_ocr": True, "force_ocr": True},
}


def version_conversor() -> str:
    import pymupdf4llm

    return f"pymupdf4llm-{getattr(pymupdf4llm, '__version__', 'desconocida')}"


def convertir(pdf: bytes, modo_ocr: str = "nunca") -> str:
    """PDF (bytes) -> Markdown con tablas. El OCR solo está disponible si la imagen lo incluye."""
    import pymupdf
    import pymupdf4llm

    with pymupdf.open(stream=pdf, filetype="pdf") as documento:
        return pymupdf4llm.to_markdown(
            documento, show_progress=False, ocr_language="spa", **MODOS_OCR[modo_ocr]
        )


# Metadatos de usuario obligatorios del contrato C1 v1 (contracts/C1_PROPUESTA.md).
METADATOS_C1 = (
    "gestora",
    "tipo-documento",
    "url-origen",
    "fecha-descarga-utc",
    "sha256",
    "correlation-id",
)


def origen_desde_pdf(
    ruta: rutas.RutaDocumento, objeto_s3: eventos.ObjetoS3, pdf: ObjetoLeido
) -> Origen:
    m = pdf.metadatos
    return Origen(
        gestora=m.get("gestora") or ruta.gestora,
        tipo_documento=m.get("tipo-documento") or ruta.tipo_documento,
        url_origen=m.get("url-origen"),
        fecha_descarga=m.get("fecha-descarga-utc") or m.get("fecha-descarga"),
        correlation_id=m.get("correlation-id") or str(uuid4()),
        pdf_bucket=objeto_s3.bucket,
        pdf_key=objeto_s3.clave,
        pdf_version_id=pdf.version_id or objeto_s3.version_id,
        pdf_sha256=pdf.sha256,
    )


def comprobar_c1(ruta: rutas.RutaDocumento, pdf: ObjetoLeido) -> list[Validacion]:
    """Fallos del contrato C1: metadatos que faltan, hash o gestora que no cuadran."""
    m = pdf.metadatos
    fallos = [
        Validacion(
            regla="metadatos_c1", campo=clave, resultado="fallo", detalle="falta"
        )
        for clave in METADATOS_C1
        if not m.get(clave)
    ]
    declarado = m.get("sha256")
    if declarado and declarado.lower() != pdf.sha256:
        fallos.append(
            Validacion(
                regla="sha256",
                resultado="fallo",
                detalle=f"declarado {declarado}, calculado {pdf.sha256}",
            )
        )
    if m.get("gestora") and m["gestora"] != ruta.gestora:
        fallos.append(
            Validacion(
                regla="gestora",
                resultado="fallo",
                detalle=f"metadato '{m['gestora']}' y clave '{ruta.gestora}'",
            )
        )
    return fallos


def procesar(objeto_s3: eventos.ObjetoS3, almacen: AlmacenS3, modo_ocr: str) -> str:
    """Procesa un PDF. Devuelve el resultado para la métrica: CONVERTIDO, OMITIDO o REJECTED."""
    cronometro = Cronometro()
    ruta = rutas.desde_clave_raw(objeto_s3.clave)
    pdf = almacen.leer(objeto_s3.bucket, objeto_s3.clave, objeto_s3.version_id)
    origen = origen_desde_pdf(ruta, objeto_s3, pdf)
    contexto = {
        "correlation_id": origen.correlation_id,
        "clave": objeto_s3.clave,
        "sha256": pdf.sha256,
    }

    fallos_c1 = comprobar_c1(ruta, pdf)
    if fallos_c1:
        motivo = (
            "sha256_no_coincide"
            if any(v.regla == "sha256" for v in fallos_c1)
            else "contrato_c1"
        )
        _rechazar(almacen, ruta, origen, motivo, fallos_c1, cronometro)
        log(
            "WARNING",
            "PDF fuera del contrato C1; no se procesa",
            motivo=motivo,
            **contexto,
        )
        metrica_resultado(ETAPA, "REJECTED", cronometro.ms, origen.correlation_id)
        return "REJECTED"

    existente = almacen.metadatos(objeto_s3.bucket, ruta.clave_markdown)
    if existente and existente.get("pdf-sha256") == pdf.sha256:
        log("INFO", "Markdown ya generado para este PDF; se omite", **contexto)
        metrica_resultado(ETAPA, "OMITIDO", cronometro.ms, origen.correlation_id)
        return "OMITIDO"

    conversor = version_conversor()
    markdown = convertir(pdf.contenido, modo_ocr)
    caracteres = len(markdown.strip())

    if caracteres < MIN_CARACTERES:
        origen = origen.model_copy(
            update={"modo_ocr": modo_ocr, "conversor": conversor}
        )
        detalle = (
            f"{caracteres} caracteres con OCR '{modo_ocr}' (mínimo {MIN_CARACTERES})"
        )
        _rechazar(
            almacen,
            ruta,
            origen,
            "markdown_vacio",
            [Validacion(regla="markdown_legible", resultado="fallo", detalle=detalle)],
            cronometro,
        )
        log(
            "WARNING",
            "PDF sin texto suficiente; requiere OCR",
            caracteres=caracteres,
            **contexto,
        )
        metrica_resultado(ETAPA, "REJECTED", cronometro.ms, origen.correlation_id)
        return "REJECTED"

    almacen.escribir(
        objeto_s3.bucket,
        ruta.clave_markdown,
        markdown.encode("utf-8"),
        "text/markdown; charset=utf-8",
        {
            "pdf-bucket": origen.pdf_bucket,
            "pdf-key": origen.pdf_key,
            "pdf-version-id": origen.pdf_version_id,
            "pdf-sha256": origen.pdf_sha256,
            "gestora": origen.gestora,
            "tipo-documento": origen.tipo_documento,
            "url-origen": origen.url_origen,
            "fecha-descarga-utc": origen.fecha_descarga,
            "correlation-id": origen.correlation_id,
            "modo-ocr": modo_ocr,
            "conversor": conversor,
            "convertido-en": datetime.now(UTC).isoformat(),
        },
    )
    log(
        "INFO",
        "Markdown generado",
        destino=ruta.clave_markdown,
        caracteres=caracteres,
        **contexto,
    )
    metrica_resultado(ETAPA, "CONVERTIDO", cronometro.ms, origen.correlation_id)
    return "CONVERTIDO"


def _rechazar(
    almacen: AlmacenS3,
    ruta: rutas.RutaDocumento,
    origen: Origen,
    motivo: str,
    validaciones: list[Validacion],
    cronometro: Cronometro,
) -> None:
    """Deja el JSON REJECTED de auditoría (C3); no se reintenta."""
    resultado = ResultadoExtraccion(
        estado=Estado.REJECTED,
        motivo=motivo,
        source=origen,
        validaciones=validaciones,
        iniciado_en=cronometro.inicio_utc,
        finalizado_en=datetime.now(UTC),
    )
    almacen.escribir(
        origen.pdf_bucket,
        ruta.clave_estructurada,
        resultado.model_dump_json(indent=2).encode("utf-8"),
        "application/json",
        {
            "pdf-sha256": origen.pdf_sha256,
            "estado": resultado.estado.value,
            "correlation-id": origen.correlation_id,
        },
    )


def handler(
    evento: dict[str, Any], contexto: Any = None, almacen: AlmacenS3 | None = None
) -> dict[str, Any]:
    """Lambda con ReportBatchItemFailures: solo se reintentan los mensajes que fallan."""
    almacen = almacen or AlmacenS3()
    modo_ocr = os.environ.get("MODO_OCR", "nunca")
    fallos = []
    for mensaje in eventos.leer_registros(evento):
        try:
            for objeto in mensaje.objetos:
                try:
                    procesar(objeto, almacen, modo_ocr)
                except rutas.ClaveNoValida as error:
                    # La notificación ya filtra raw/ + _kid.pdf; reintentar no lo arregla.
                    log(
                        "ERROR",
                        "Clave fuera del contrato C1; se descarta",
                        error=str(error),
                        clave=objeto.clave,
                    )
                    metrica_resultado(ETAPA, "REJECTED", 0)
        except Exception as error:
            log(
                "ERROR",
                "Error técnico; SQS reintentará",
                error=repr(error),
                message_id=mensaje.message_id,
                intento=mensaje.intentos,
            )
            metrica_resultado(ETAPA, "FALLO_INTENTO", 0)
            fallos.append({"itemIdentifier": mensaje.message_id})
    return {"batchItemFailures": fallos}
