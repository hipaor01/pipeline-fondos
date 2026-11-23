"""Lectura de los mensajes SQS que disparan cada etapa.

La cola recibe eventos `Object Created` de S3 a través de EventBridge (la regla
filtra prefijo y sufijo, ver `infra/modules/processing`). También se acepta el
formato de notificación directa de S3 por si en algún momento se cambia.
"""

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote_plus


class EventoNoValido(ValueError):
    """El mensaje no contiene un evento de objeto creado en S3."""


@dataclass(frozen=True, slots=True)
class ObjetoS3:
    bucket: str
    clave: str
    version_id: str | None


@dataclass(frozen=True, slots=True)
class MensajeSQS:
    message_id: str
    intentos: int  # ApproximateReceiveCount: 1 en el primer intento
    objeto: ObjetoS3 | None  # None si es un evento de prueba de S3


def leer_registros(evento_lambda: dict[str, Any]) -> list[MensajeSQS]:
    return [_leer_registro(registro) for registro in evento_lambda.get("Records", [])]


def _leer_registro(registro: dict[str, Any]) -> MensajeSQS:
    atributos = registro.get("attributes", {})
    try:
        cuerpo = json.loads(registro["body"])
    except (KeyError, json.JSONDecodeError) as error:
        raise EventoNoValido(f"Cuerpo SQS no es JSON: {error}") from error
    return MensajeSQS(
        message_id=registro.get("messageId", ""),
        intentos=int(atributos.get("ApproximateReceiveCount", "1")),
        objeto=_objeto_de_cuerpo(cuerpo),
    )


def _objeto_de_cuerpo(cuerpo: dict[str, Any]) -> ObjetoS3 | None:
    # EventBridge: la clave llega sin codificar.
    if cuerpo.get("source") == "aws.s3" and "detail" in cuerpo:
        detalle = cuerpo["detail"]
        return ObjetoS3(
            bucket=detalle["bucket"]["name"],
            clave=detalle["object"]["key"],
            version_id=detalle["object"].get("version-id"),
        )
    # Notificación directa de S3: la clave llega codificada como URL.
    if cuerpo.get("Event") == "s3:TestEvent":
        return None
    if "Records" in cuerpo and cuerpo["Records"]:
        s3 = cuerpo["Records"][0]["s3"]
        return ObjetoS3(
            bucket=s3["bucket"]["name"],
            clave=unquote_plus(s3["object"]["key"]),
            version_id=s3["object"].get("versionId"),
        )
    raise EventoNoValido(f"Formato de evento desconocido: claves {sorted(cuerpo)}")
