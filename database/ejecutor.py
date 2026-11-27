"""Ejecutores SQL compartidos para Aurora Data API y PostgreSQL local.

El SQL se escribe con parametros ``:nombre`` (formato de la Data API). En local
y en los tests se usa psycopg contra PostgreSQL, de modo que se ejecutan las
mismas sentencias y se emulan los tipos enviados por la Data API.
"""

import json
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any, Protocol

Parametros = dict[str, Any]


class EjecutorSQL(Protocol):
    """Contrato comun para ejecutar SQL desde cualquier componente."""

    def ejecutar(
        self, sql: str, parametros: Parametros | None = None
    ) -> list[dict[str, Any]]: ...

    def transaccion(self) -> Any: ...


class ErrorBaseDatos(RuntimeError):
    """Error tecnico producido durante una operacion de base de datos."""


class EjecutorDataAPI:
    """Ejecuta SQL en Aurora PostgreSQL mediante RDS Data API."""

    ESPERA_REANUDACION_S = 40

    def __init__(
        self, cluster_arn: str, secret_arn: str, base_datos: str, cliente: Any = None
    ) -> None:
        if cliente is None:
            import boto3  # type: ignore[import-untyped]

            cliente = boto3.client("rds-data")
        self._cliente = cliente
        self._base = {
            "resourceArn": cluster_arn,
            "secretArn": secret_arn,
            "database": base_datos,
        }
        self._transaccion_id: str | None = None

    def ejecutar(
        self, sql: str, parametros: Parametros | None = None
    ) -> list[dict[str, Any]]:
        peticion: dict[str, Any] = {
            **self._base,
            "sql": sql,
            "parameters": [
                _a_parametro_data_api(nombre, valor)
                for nombre, valor in (parametros or {}).items()
            ],
            "formatRecordsAs": "JSON",
        }
        if self._transaccion_id:
            peticion["transactionId"] = self._transaccion_id
        respuesta = self._con_reanudacion(
            lambda: self._cliente.execute_statement(**peticion)
        )
        return json.loads(respuesta.get("formattedRecords") or "[]")

    @contextmanager
    def transaccion(self) -> Iterator[None]:
        if self._transaccion_id:
            raise ErrorBaseDatos("No se admiten transacciones anidadas")
        inicio = self._con_reanudacion(
            lambda: self._cliente.begin_transaction(**self._base)
        )
        self._transaccion_id = inicio["transactionId"]
        try:
            yield
            self._cliente.commit_transaction(
                resourceArn=self._base["resourceArn"],
                secretArn=self._base["secretArn"],
                transactionId=self._transaccion_id,
            )
        except BaseException:
            self._cliente.rollback_transaction(
                resourceArn=self._base["resourceArn"],
                secretArn=self._base["secretArn"],
                transactionId=self._transaccion_id,
            )
            raise
        finally:
            self._transaccion_id = None

    def _con_reanudacion(self, llamada: Any) -> Any:
        limite = time.monotonic() + self.ESPERA_REANUDACION_S
        while True:
            try:
                return llamada()
            except Exception as error:  # botocore genera la clase dinamicamente
                codigo = getattr(error, "response", {}).get("Error", {}).get("Code", "")
                if codigo != "DatabaseResumingException" or time.monotonic() > limite:
                    raise
                time.sleep(3)


def _a_parametro_data_api(nombre: str, valor: Any) -> dict[str, Any]:
    if valor is None:
        return {"name": nombre, "value": {"isNull": True}}
    if isinstance(valor, bool):
        return {"name": nombre, "value": {"booleanValue": valor}}
    if isinstance(valor, int):
        return {"name": nombre, "value": {"longValue": valor}}
    if isinstance(valor, float):
        return {
            "name": nombre,
            "value": {"stringValue": repr(valor)},
            "typeHint": "DECIMAL",
        }
    if isinstance(valor, datetime):
        utc = valor.astimezone(UTC).replace(tzinfo=None)
        texto = utc.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        return {
            "name": nombre,
            "value": {"stringValue": texto},
            "typeHint": "TIMESTAMP",
        }
    if isinstance(valor, date):
        return {
            "name": nombre,
            "value": {"stringValue": valor.isoformat()},
            "typeHint": "DATE",
        }
    return {"name": nombre, "value": {"stringValue": str(valor)}}


_PARAMETRO = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")


class EjecutorPsycopg:
    """Ejecuta el mismo SQL directamente en PostgreSQL local."""

    def __init__(self, dsn: str) -> None:
        import psycopg  # type: ignore[import-not-found]
        from psycopg.rows import dict_row  # type: ignore[import-not-found]

        self._conexion = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)

    def ejecutar(
        self, sql: str, parametros: Parametros | None = None
    ) -> list[dict[str, Any]]:
        if parametros:
            tipos = {nombre: _tipo_data_api(valor) for nombre, valor in parametros.items()}

            def sustituir(coincidencia: re.Match[str]) -> str:
                nombre = coincidencia.group(1)
                tipo = tipos.get(nombre)
                return f"CAST(%({nombre})s AS {tipo})" if tipo else f"%({nombre})s"

            sql = _PARAMETRO.sub(sustituir, sql.replace("%", "%%"))
        with self._conexion.cursor() as cursor:
            cursor.execute(sql, parametros or None)
            filas = cursor.fetchall() if cursor.description else []
        return [
            {clave: _serializable(valor) for clave, valor in fila.items()}
            for fila in filas
        ]

    @contextmanager
    def transaccion(self) -> Iterator[None]:
        with self._conexion.transaction():
            yield

    def cerrar(self) -> None:
        self._conexion.close()


def _tipo_data_api(valor: Any) -> str | None:
    """Devuelve el tipo con el que Data API enviaria el valor."""

    if valor is None:
        return None
    if isinstance(valor, bool):
        return "boolean"
    if isinstance(valor, int):
        return "bigint"
    if isinstance(valor, float):
        return "numeric"
    if isinstance(valor, datetime):
        return "timestamp"
    if isinstance(valor, date):
        return "date"
    return "varchar"


def _serializable(valor: Any) -> Any:
    """Imita los valores JSON devueltos por Data API."""

    from decimal import Decimal

    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    return valor
