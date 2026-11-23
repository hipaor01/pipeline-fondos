"""Tests sin dependencias externas: rutas, eventos, esquema, validación y Bedrock."""

import json

import pytest

from procesamiento import eventos, rutas
from procesamiento.bedrock import ExtractorBedrock, RespuestaIncompleta
from procesamiento.datos.ejecutor import _a_parametro_data_api
from procesamiento.datos.migraciones import sentencias
from procesamiento.esquema import (
    ESQUEMA_BEDROCK,
    RUTA_CONTRATO,
    Estado,
    isin_valido,
    texto_contrato,
)
from procesamiento.validacion import validar_extraccion
from tests.procesamiento.conftest import evento_sqs

# ----------------------------------------------------------------- rutas (C1 -> C2 -> C3)


def test_claves_derivadas_de_la_clave_raw():
    ruta = rutas.desde_clave_raw(
        "raw/bestinver/20261119/bestinfond_datos_fundamentales.pdf"
    )
    assert (
        ruta.clave_markdown
        == "processed/markdown/bestinver/20261119/bestinfond_datos_fundamentales.md"
    )
    assert (
        ruta.clave_estructurada
        == "processed/structured/bestinver/20261119/bestinfond_datos_fundamentales.json"
    )
    assert ruta.tipo_documento == "datos_fundamentales"
    assert rutas.desde_clave_markdown(ruta.clave_markdown) == ruta


@pytest.mark.parametrize(
    "clave",
    [
        "bestinver/20261119/bestinfond_datos_fundamentales.pdf",  # formato antiguo, sin raw/
        "raw/bestinver/2026-11-19/x.pdf",
        "raw/Bestinver/20261119/x.pdf",
        "raw/bestinver/20261119/x.md",
    ],
)
def test_claves_fuera_de_contrato(clave):
    with pytest.raises(rutas.ClaveNoValida):
        rutas.desde_clave_raw(clave)


# ----------------------------------------------------------------- eventos SQS


def test_evento_eventbridge():
    [mensaje] = eventos.leer_registros(
        evento_sqs("raw/a/20260101/b_datos_fundamentales.pdf", intentos=2)
    )
    assert mensaje.objeto.clave == "raw/a/20260101/b_datos_fundamentales.pdf"
    assert mensaje.intentos == 2


def test_evento_notificacion_s3_decodifica_la_clave():
    cuerpo = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "b"},
                    "object": {"key": "raw/a/20260101/con+espacio.pdf"},
                }
            }
        ]
    }
    [mensaje] = eventos.leer_registros(
        {"Records": [{"messageId": "1", "body": json.dumps(cuerpo)}]}
    )
    assert mensaje.objeto.clave == "raw/a/20260101/con espacio.pdf"


def test_evento_de_prueba_de_s3_se_ignora():
    [mensaje] = eventos.leer_registros(
        {"Records": [{"messageId": "1", "body": '{"Event": "s3:TestEvent"}'}]}
    )
    assert mensaje.objeto is None


# ----------------------------------------------------------------- esquema


@pytest.mark.parametrize(
    "isin,valido",
    [("ES0114673033", True), ("ES0114673034", False), ("LU1598757687", True)],
)
def test_digito_control_isin(isin, valido):
    assert isin_valido(isin) is valido


def _recorrer(nodo):
    if isinstance(nodo, dict):
        yield nodo
        for valor in nodo.values():
            yield from _recorrer(valor)
    elif isinstance(nodo, list):
        for valor in nodo:
            yield from _recorrer(valor)


def test_esquema_bedrock_respeta_los_limites_de_salida_estructurada():
    props = ESQUEMA_BEDROCK["properties"]
    assert ESQUEMA_BEDROCK["additionalProperties"] is False
    assert set(ESQUEMA_BEDROCK["required"]) == set(
        props
    )  # 0 propiedades opcionales (máx. 12)
    assert sum(isinstance(p["type"], list) for p in props.values()) <= 16
    prohibidas = {"minimum", "maximum", "multipleOf", "minLength", "maxLength", "anyOf"}
    for nodo in _recorrer(ESQUEMA_BEDROCK):
        assert not prohibidas & set(nodo), nodo


def test_contrato_c3_actualizado():
    assert RUTA_CONTRATO.read_text(encoding="utf-8") == texto_contrato(), (
        "Regenera el contrato con: python -m procesamiento.esquema"
    )


# ----------------------------------------------------------------- validación


def test_respuesta_correcta_es_valid(respuesta_bestinfond, markdown_bestinfond):
    r = validar_extraccion(respuesta_bestinfond, markdown_bestinfond)
    assert r.estado is Estado.VALID, r.motivo
    assert r.datos.gastos_corrientes_pct == 1.8
    assert all(e.encontrada for e in r.evidencias.values())
    # «No cobramos comisión de entrada» para un 0 %: aviso, no rechazo.
    assert any(
        v.campo == "costes_entrada_pct" and v.resultado == "aviso"
        for v in r.validaciones
    )


def test_evidencia_inventada_rechaza(respuesta_bestinfond, markdown_bestinfond):
    respuesta_bestinfond["gastos_corrientes_pct"] = 1.5
    respuesta_bestinfond["gastos_corrientes_pct_evidencia"] = (
        "1,5 % del valor de su inversión al año."
    )
    r = validar_extraccion(respuesta_bestinfond, markdown_bestinfond)
    assert r.estado is Estado.REJECTED
    assert r.motivo == "evidencia(gastos_corrientes_pct)"


def test_valor_sin_evidencia_rechaza(respuesta_bestinfond, markdown_bestinfond):
    respuesta_bestinfond["periodo_mantenimiento_anios_evidencia"] = ""
    assert (
        validar_extraccion(respuesta_bestinfond, markdown_bestinfond).estado
        is Estado.REJECTED
    )


def test_falta_campo_obligatorio_rechaza(respuesta_bestinfond, markdown_bestinfond):
    respuesta_bestinfond["sri"] = None
    respuesta_bestinfond["sri_evidencia"] = ""
    r = validar_extraccion(respuesta_bestinfond, markdown_bestinfond)
    assert r.estado is Estado.REJECTED and "obligatorio(sri)" in r.motivo


@pytest.mark.parametrize(
    "campo,valor", [("sri", 9), ("isin", "ES0114673034"), ("gastos_corrientes_pct", -1)]
)
def test_valores_fuera_de_rango_rechazan(
    respuesta_bestinfond, markdown_bestinfond, campo, valor
):
    respuesta_bestinfond[campo] = valor
    r = validar_extraccion(respuesta_bestinfond, markdown_bestinfond)
    assert r.estado is Estado.REJECTED and r.datos is None


def test_isin_que_no_esta_en_su_evidencia_rechaza(
    respuesta_bestinfond, markdown_bestinfond
):
    respuesta_bestinfond["isin"] = "LU1598757687"
    r = validar_extraccion(respuesta_bestinfond, markdown_bestinfond)
    assert r.estado is Estado.REJECTED and "coherencia(isin)" in r.motivo


# ----------------------------------------------------------------- Bedrock


class ClienteConverse:
    def __init__(self, respuesta):
        self.respuesta, self.peticiones = respuesta, []

    def converse(self, **peticion):
        self.peticiones.append(peticion)
        return self.respuesta


def test_peticion_usa_salida_estructurada_nativa(respuesta_bestinfond):
    cliente = ClienteConverse(
        {
            "output": {
                "message": {"content": [{"text": json.dumps(respuesta_bestinfond)}]}
            },
            "stopReason": "end_turn",
            "usage": {"inputTokens": 3000, "outputTokens": 300},
            "metrics": {"latencyMs": 900},
        }
    )
    extractor = ExtractorBedrock("global.modelo", "eu-west-3", cliente=cliente)
    respuesta = extractor.extraer("# KID")
    formato = cliente.peticiones[0]["outputConfig"]["textFormat"]
    assert formato["type"] == "json_schema"
    assert json.loads(formato["structure"]["jsonSchema"]["schema"]) == ESQUEMA_BEDROCK
    assert cliente.peticiones[0]["inferenceConfig"]["temperature"] == 0
    assert (
        respuesta.datos["isin"] == "ES0114673033" and respuesta.tokens_entrada == 3000
    )


def test_respuesta_truncada_es_error_tecnico():
    cliente = ClienteConverse(
        {
            "output": {"message": {"content": [{"text": "{"}]}},
            "stopReason": "max_tokens",
        }
    )
    with pytest.raises(RespuestaIncompleta):
        ExtractorBedrock("m", "eu-west-3", cliente=cliente).extraer("x")


# ----------------------------------------------------------------- Data API y migraciones


def test_parametros_data_api():
    from datetime import UTC, date, datetime

    assert _a_parametro_data_api("a", None) == {"name": "a", "value": {"isNull": True}}
    assert _a_parametro_data_api("a", 4)["value"] == {"longValue": 4}
    assert _a_parametro_data_api("a", 1.8)["typeHint"] == "DECIMAL"
    assert (
        _a_parametro_data_api("a", date(2025, 12, 31))["value"]["stringValue"]
        == "2025-12-31"
    )
    ts = _a_parametro_data_api("a", datetime(2026, 1, 1, 10, 0, tzinfo=UTC))
    assert ts == {
        "name": "a",
        "value": {"stringValue": "2026-01-01 10:00:00.000"},
        "typeHint": "TIMESTAMP",
    }


def test_separador_de_sentencias():
    sql = "-- comentario; con punto y coma\nCREATE TABLE a (x int);\nINSERT INTO a VALUES\n  (1),\n  (2);\n"
    assert sentencias(sql) == [
        "CREATE TABLE a (x int)",
        "INSERT INTO a VALUES\n  (1),\n  (2)",
    ]
