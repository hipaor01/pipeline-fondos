"""Dobles de S3 y Bedrock y un PostgreSQL real para los tests de la capa P2.

PostgreSQL: se usa TEST_DATABASE_URL si está definida (p. ej. un service container
en GitHub Actions); si no, se arranca un servidor temporal con `initdb`/`pg_ctl`
si están instalados. Si no hay ninguno, los tests de base de datos se omiten.
"""

import copy
import glob
import io
import json
import os
import shutil
import socket
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pytest

from procesamiento.bedrock import RespuestaModelo

FIXTURES = Path(__file__).parent / "fixtures"
BUCKET = "documentos-test"


# --------------------------------------------------------------------------- S3


class ErrorS3(Exception):
    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.response = {"Error": {"Code": codigo}}


class S3EnMemoria:
    """Implementa get_object, head_object y put_object con versionado."""

    def __init__(self) -> None:
        self.objetos: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.escrituras: list[str] = []

    def put_object(
        self,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str = "",
        Metadata: dict | None = None,
    ) -> dict:
        versiones = self.objetos.setdefault((Bucket, Key), [])
        version = f"v{len(versiones) + 1}"
        versiones.append(
            {
                "Body": Body,
                "Metadata": dict(Metadata or {}),
                "ContentType": ContentType,
                "VersionId": version,
            }
        )
        self.escrituras.append(Key)
        return {"VersionId": version}

    def _version(self, Bucket: str, Key: str, VersionId: str | None = None) -> dict:
        versiones = self.objetos.get((Bucket, Key))
        if not versiones:
            raise ErrorS3("NoSuchKey")
        if VersionId:
            return next(v for v in versiones if v["VersionId"] == VersionId)
        return versiones[-1]

    def get_object(self, Bucket: str, Key: str, VersionId: str | None = None) -> dict:
        v = self._version(Bucket, Key, VersionId)
        return {
            "Body": io.BytesIO(v["Body"]),
            "Metadata": v["Metadata"],
            "VersionId": v["VersionId"],
        }

    def head_object(self, Bucket: str, Key: str) -> dict:
        try:
            v = self._version(Bucket, Key)
        except ErrorS3:
            raise ErrorS3("404") from None
        return {"Metadata": v["Metadata"], "VersionId": v["VersionId"]}

    def json(self, clave: str) -> dict:
        return json.loads(self._version(BUCKET, clave)["Body"])


@pytest.fixture
def s3() -> S3EnMemoria:
    return S3EnMemoria()


def evento_sqs(
    *claves: str, intentos: int = 1, bucket: str = BUCKET, version_id: str | None = None
) -> dict:
    """Mensaje SQS con una notificación nativa de S3 (contrato C1 v1).

    La clave va codificada como formulario URL, como la envía S3; varias claves
    van como varios `Records` del mismo mensaje.
    """
    cuerpo = {
        "Records": [
            {
                "eventSource": "aws:s3",
                "eventName": "ObjectCreated:Put",
                "s3": {
                    "bucket": {"name": bucket},
                    "object": {"key": quote_plus(clave), "versionId": version_id},
                },
            }
            for clave in claves
        ]
    }
    return {
        "Records": [
            {
                "messageId": f"msg-{claves[0]}",
                "body": json.dumps(cuerpo),
                "attributes": {"ApproximateReceiveCount": str(intentos)},
            }
        ]
    }


# --------------------------------------------------------------------------- Bedrock


class BedrockFalso:
    """Sustituye a ExtractorBedrock: devuelve una respuesta fija y cuenta llamadas."""

    model_id = "modelo.falso-v1"
    region = "eu-west-3"

    def __init__(self, respuesta: dict | Exception) -> None:
        self.respuesta = respuesta
        self.llamadas = 0

    def extraer(self, markdown: str) -> RespuestaModelo:
        self.llamadas += 1
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return RespuestaModelo(
            copy.deepcopy(self.respuesta), 1234.0, 3000, 400, "end_turn"
        )


@pytest.fixture
def respuesta_bestinfond() -> dict:
    return json.loads(
        (FIXTURES / "bestinfond_respuesta_bedrock.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def markdown_bestinfond() -> str:
    return (FIXTURES / "bestinfond_datos_fundamentales.md").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- PostgreSQL


def _binarios_postgres() -> Path | None:
    for candidato in [
        shutil.which("pg_ctl"),
        *glob.glob("/usr/lib/postgresql/*/bin/pg_ctl"),
    ]:
        if candidato:
            return Path(candidato).parent
    return None


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def postgres_dsn() -> Iterator[str]:
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return
    binarios = _binarios_postgres()
    if binarios is None:
        pytest.skip("No hay PostgreSQL disponible (define TEST_DATABASE_URL)")
    directorio = Path(tempfile.mkdtemp(prefix="pg-test-"))
    usuario = {}
    if os.geteuid() == 0:  # postgres no arranca como root
        import pwd

        nobody = pwd.getpwnam("nobody")
        shutil.chown(directorio, nobody.pw_uid, nobody.pw_gid)
        usuario = {"user": nobody.pw_uid, "group": nobody.pw_gid}
    datos, puerto = directorio / "datos", _puerto_libre()
    subprocess.run(
        [binarios / "initdb", "-D", datos, "-U", "postgres", "-A", "trust"],
        check=True,
        capture_output=True,
        **usuario,
    )
    subprocess.run(
        [
            binarios / "pg_ctl",
            "-D",
            datos,
            "-o",
            f"-p {puerto} -k {directorio} -h 127.0.0.1",
            "-w",
            "start",
            "-l",
            directorio / "log",
        ],
        check=True,
        capture_output=True,
        **usuario,
    )
    try:
        yield f"postgresql://postgres@127.0.0.1:{puerto}/postgres"
    finally:
        subprocess.run(
            [binarios / "pg_ctl", "-D", datos, "-m", "fast", "stop"],
            capture_output=True,
            **usuario,
        )
        shutil.rmtree(directorio, ignore_errors=True)


@pytest.fixture
def ejecutor(postgres_dsn: str) -> Iterator[Any]:
    """Base de datos limpia y migrada para cada test."""
    from database.ejecutor import EjecutorPsycopg
    from procesamiento.datos.migraciones import aplicar

    admin = EjecutorPsycopg(postgres_dsn)
    admin.ejecutar("DROP DATABASE IF EXISTS fondos_test WITH (FORCE)")
    admin.ejecutar("CREATE DATABASE fondos_test")
    admin.cerrar()
    dsn = postgres_dsn.rsplit("/", 1)[0] + "/fondos_test"
    ejecutor = EjecutorPsycopg(dsn)
    aplicar(ejecutor)
    yield ejecutor
    ejecutor.cerrar()
