"""Lectura de los mensajes SQS que disparan cada etapa.

Contrato C1 v1 (P1): notificación nativa S3 `ObjectCreated` -> SQS estándar. Un
mensaje puede traer varios `Records`; se procesan todos. La clave llega
codificada como formulario URL y se decodifica con `unquote_plus`. Se usa el
`versionId` del evento para leer exactamente la versión que lo causó.

También se acepta el formato de EventBridge por si se cambia el transporte.
"""

import json
from dataclasses import dataclass, field
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
    objetos: list[ObjetoS3] = field(default_factory=list)  # vacío si es s3:TestEvent


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
        objetos=_objetos_de_cuerpo(cuerpo),
    )


def _objetos_de_cuerpo(cuerpo: dict[str, Any]) -> list[ObjetoS3]:
    if cuerpo.get("Event") == "s3:TestEvent":
        return []
    # Notificación nativa de S3 (C1): clave codificada, puede haber varios Records.
    if "Records" in cuerpo:
        objetos = []
        for record in cuerpo["Records"]:
            if not str(record.get("eventName", "ObjectCreated")).startswith(
                "ObjectCreated"
            ):
                continue
            s3 = record["s3"]
            objetos.append(
                ObjetoS3(
                    bucket=s3["bucket"]["name"],
                    clave=unquote_plus(s3["object"]["key"]),
                    version_id=s3["object"].get("versionId"),
                )
            )
        return objetos
    # EventBridge: la clave llega sin codificar.
    if cuerpo.get("source") == "aws.s3" and "detail" in cuerpo:
        detalle = cuerpo["detail"]
        return [
            ObjetoS3(
                bucket=detalle["bucket"]["name"],
                clave=detalle["object"]["key"],
                version_id=detalle["object"].get("version-id"),
            )
        ]
    raise EventoNoValido(f"Formato de evento desconocido: claves {sorted(cuerpo)}")
