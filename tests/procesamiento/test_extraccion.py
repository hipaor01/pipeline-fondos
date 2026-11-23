"""Etapa de extracción de principio a fin: S3 en memoria, Bedrock simulado y PostgreSQL real."""

import hashlib

import pytest

from api.models.fondo import FondoDetalle
from api.models.kid import KidVersion
from procesamiento import extraccion
from procesamiento.almacen import AlmacenS3
from procesamiento.datos.migraciones import aplicar
from procesamiento.datos.repositorio import RepositorioKids
from tests.procesamiento.conftest import BUCKET, BedrockFalso, evento_sqs

SHA = hashlib.sha256(b"pdf de bestinfond").hexdigest()


def _subir_markdown(
    s3, markdown, fecha="20261119", nombre="bestinfond_datos_fundamentales", sha=SHA
):
    clave = f"processed/markdown/bestinver/{fecha}/{nombre}.md"
    s3.put_object(
        Bucket=BUCKET,
        Key=clave,
        Body=markdown.encode(),
        Metadata={
            "pdf-bucket": BUCKET,
            "pdf-key": f"raw/bestinver/{fecha}/{nombre}.pdf",
            "pdf-version-id": "v1",
            "pdf-sha256": sha,
            "gestora": "bestinver",
            "tipo-documento": nombre.split("_", 1)[1],
            "url-origen": "https://www.bestinver.es/x.pdf",
            "fecha-descarga": "2026-11-19T06:00:00+00:00",
            "correlation-id": "corr-1",
            "modo-ocr": "nunca",
            "conversor": "pymupdf4llm-2.1",
        },
    )
    return clave


def _dependencias(s3, ejecutor, bedrock):
    return extraccion.Dependencias(
        almacen=AlmacenS3(s3),
        extractor=bedrock,
        repositorio=RepositorioKids(ejecutor),
        tipos_kid=frozenset({"datos_fundamentales"}),
        max_intentos=3,
    )


def _cuenta(ejecutor, tabla):
    return ejecutor.ejecutar(f"SELECT count(*) AS n FROM {tabla}")[0]["n"]


def test_kid_valido_se_audita_y_se_carga(
    s3, ejecutor, markdown_bestinfond, respuesta_bestinfond
):
    clave = _subir_markdown(s3, markdown_bestinfond)
    bedrock = BedrockFalso(respuesta_bestinfond)

    respuesta = extraccion.handler(
        evento_sqs(clave), dependencias=_dependencias(s3, ejecutor, bedrock)
    )

    assert respuesta == {"batchItemFailures": []}
    auditoria = s3.json(clave.replace("markdown", "structured").replace(".md", ".json"))
    assert auditoria["estado"] == "VALID" and auditoria["schema_version"] == "1.0.0"
    assert (
        auditoria["source"]["pdf_sha256"] == SHA
        and auditoria["source"]["correlation_id"] == "corr-1"
    )
    assert auditoria["modelo"]["tokens_entrada"] == 3000
    assert auditoria["evidencias"]["isin"]["encontrada"] is True
    [kid] = ejecutor.ejecutar("SELECT * FROM api_kid_version")
    assert kid["isin"] == "ES0114673033" and kid["gestora_nombre"] == "Bestinver"
    assert (
        kid["fecha_documento"] == "2025-12-31" and kid["gastos_corrientes_pct"] == 1.8
    )


def test_las_vistas_cumplen_los_modelos_de_la_api(
    s3, ejecutor, markdown_bestinfond, respuesta_bestinfond
):
    """Contrato C4: lo que devuelven las vistas valida contra los modelos Pydantic de P3."""
    clave = _subir_markdown(s3, markdown_bestinfond)
    extraccion.handler(
        evento_sqs(clave),
        dependencias=_dependencias(s3, ejecutor, BedrockFalso(respuesta_bestinfond)),
    )

    def con_gestora(fila):
        fila = dict(fila)
        fila["gestora"] = {
            "codigo": fila.pop("gestora_codigo"),
            "nombre": fila.pop("gestora_nombre"),
        }
        return fila

    [kid] = ejecutor.ejecutar("SELECT * FROM api_kid_version")
    KidVersion.model_validate(con_gestora(kid))
    [fondo] = ejecutor.ejecutar("SELECT * FROM api_fondo")
    assert (
        FondoDetalle.model_validate(con_gestora(fondo)).fecha_ultimo_kid.isoformat()
        == "2025-12-31"
    )


def test_reentrega_del_mensaje_no_duplica_ni_llama_a_bedrock(
    s3, ejecutor, markdown_bestinfond, respuesta_bestinfond
):
    clave = _subir_markdown(s3, markdown_bestinfond)
    bedrock = BedrockFalso(respuesta_bestinfond)
    dep = _dependencias(s3, ejecutor, bedrock)

    extraccion.handler(evento_sqs(clave), dependencias=dep)
    extraccion.handler(evento_sqs(clave, intentos=2), dependencias=dep)

    assert bedrock.llamadas == 1
    assert _cuenta(ejecutor, "kid_version") == 1 and _cuenta(ejecutor, "documento") == 1


def test_mismo_pdf_descargado_otro_dia_no_crea_otra_version(
    s3, ejecutor, markdown_bestinfond, respuesta_bestinfond
):
    bedrock = BedrockFalso(respuesta_bestinfond)
    dep = _dependencias(s3, ejecutor, bedrock)
    extraccion.handler(
        evento_sqs(_subir_markdown(s3, markdown_bestinfond, fecha="20261119")),
        dependencias=dep,
    )

    clave_dia2 = _subir_markdown(s3, markdown_bestinfond, fecha="20261120")
    extraccion.handler(evento_sqs(clave_dia2), dependencias=dep)

    assert bedrock.llamadas == 1
    assert _cuenta(ejecutor, "kid_version") == 1
    auditoria = s3.json(
        clave_dia2.replace("markdown", "structured").replace(".md", ".json")
    )
    assert auditoria["estado"] == "VALID" and auditoria["duplicado"] is True


def test_cargar_dos_veces_el_mismo_resultado_es_idempotente(
    s3, ejecutor, markdown_bestinfond, respuesta_bestinfond
):
    clave = _subir_markdown(s3, markdown_bestinfond)
    extraccion.handler(
        evento_sqs(clave),
        dependencias=_dependencias(s3, ejecutor, BedrockFalso(respuesta_bestinfond)),
    )
    clave_json = clave.replace("markdown", "structured").replace(".md", ".json")
    resultado = extraccion.ResultadoExtraccion.model_validate(s3.json(clave_json))

    carga = RepositorioKids(ejecutor).guardar(resultado, clave_json)

    assert carga.insertado is False
    for tabla in ("gestora", "fondo", "clase_fondo", "documento", "kid_version"):
        assert _cuenta(ejecutor, tabla) == (3 if tabla == "gestora" else 1), tabla


def test_ficha_del_fondo_se_rechaza_sin_llamar_a_bedrock(
    s3, ejecutor, respuesta_bestinfond
):
    clave = _subir_markdown(
        s3, "# Ficha mensual\n" * 50, nombre="bestinfond_ficha_fondo"
    )
    bedrock = BedrockFalso(respuesta_bestinfond)

    extraccion.handler(
        evento_sqs(clave), dependencias=_dependencias(s3, ejecutor, bedrock)
    )

    assert bedrock.llamadas == 0
    assert (
        s3.json(clave.replace("markdown", "structured").replace(".md", ".json"))[
            "motivo"
        ]
        == "no_es_kid"
    )


def test_rechazado_se_audita_pero_no_llega_a_aurora(
    s3, ejecutor, markdown_bestinfond, respuesta_bestinfond
):
    respuesta_bestinfond["sri"], respuesta_bestinfond["sri_evidencia"] = (
        6,
        "clase de riesgo 6",
    )
    clave = _subir_markdown(s3, markdown_bestinfond)
    bedrock = BedrockFalso(respuesta_bestinfond)
    dep = _dependencias(s3, ejecutor, bedrock)

    assert extraccion.handler(evento_sqs(clave), dependencias=dep) == {
        "batchItemFailures": []
    }
    extraccion.handler(
        evento_sqs(clave, intentos=2), dependencias=dep
    )  # no se reintenta

    auditoria = s3.json(clave.replace("markdown", "structured").replace(".md", ".json"))
    assert auditoria["estado"] == "REJECTED" and auditoria["datos"] is None
    assert auditoria["datos_crudos"]["sri"] == 6
    assert bedrock.llamadas == 1 and _cuenta(ejecutor, "kid_version") == 0


@pytest.mark.parametrize("intento,json_error", [(1, False), (3, True)])
def test_error_de_bedrock_se_reintenta_y_en_el_ultimo_intento_se_audita(
    s3, ejecutor, markdown_bestinfond, intento, json_error
):
    clave = _subir_markdown(s3, markdown_bestinfond)
    dep = _dependencias(s3, ejecutor, BedrockFalso(TimeoutError("Bedrock no responde")))

    respuesta = extraccion.handler(
        evento_sqs(clave, intentos=intento), dependencias=dep
    )

    assert respuesta == {"batchItemFailures": [{"itemIdentifier": f"msg-{clave}"}]}
    clave_json = clave.replace("markdown", "structured").replace(".md", ".json")
    assert (clave_json in s3.escrituras) is json_error
    if json_error:
        assert s3.json(clave_json)["estado"] == "ERROR"


def test_migraciones_son_idempotentes(ejecutor):
    assert aplicar(ejecutor) == []
    assert _cuenta(ejecutor, "schema_migraciones") == 2
