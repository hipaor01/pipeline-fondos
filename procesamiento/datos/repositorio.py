"""Escritura idempotente de una extracción VALID en Aurora (contrato C4).

Todo se hace en una transacción: o se cargan gestora, fondo, clase, documento y
versión del KID, o no se carga nada. Repetir la carga del mismo JSON no crea filas.
"""

from dataclasses import dataclass

from procesamiento.datos.ejecutor import EjecutorSQL
from procesamiento.esquema import Estado, ResultadoExtraccion

SQL_DOCUMENTO_CARGADO = """
SELECT d.id
FROM documento d
JOIN kid_version k ON k.documento_id = d.id
WHERE d.sha256 = :sha256
LIMIT 1
"""

SQL_GESTORA = """
INSERT INTO gestora (codigo, nombre) VALUES (:codigo, :nombre)
ON CONFLICT (codigo) DO NOTHING
"""

SQL_FONDO = """
INSERT INTO fondo (gestora_codigo, nombre_producto) VALUES (:gestora, :nombre_producto)
ON CONFLICT ON CONSTRAINT fondo_gestora_nombre_uk
DO UPDATE SET nombre_producto = EXCLUDED.nombre_producto
RETURNING id
"""

SQL_CLASE = """
INSERT INTO clase_fondo (isin, fondo_id) VALUES (:isin, :fondo_id)
ON CONFLICT (isin) DO NOTHING
"""

SQL_DOCUMENTO = """
INSERT INTO documento (
    sha256, gestora_codigo, tipo_documento, s3_bucket, s3_key, s3_version_id,
    url_origen, fecha_descarga, correlation_id, json_s3_key
) VALUES (
    :sha256, :gestora, :tipo_documento, :s3_bucket, :s3_key, :s3_version_id,
    :url_origen, :fecha_descarga, :correlation_id, :json_s3_key
)
ON CONFLICT ON CONSTRAINT documento_sha256_uk DO NOTHING
"""

SQL_ID_DOCUMENTO = "SELECT id FROM documento WHERE sha256 = :sha256"

SQL_KID_VERSION = """
INSERT INTO kid_version (
    documento_id, isin, nombre_producto, nombre_clase, gestora_productor, fecha_documento, sri,
    periodo_mantenimiento_anios, gastos_corrientes_pct, costes_entrada_pct, costes_salida_pct,
    schema_version, modelo_id, extraido_en
) VALUES (
    :documento_id, :isin, :nombre_producto, :nombre_clase, :gestora_productor, :fecha_documento, :sri,
    :periodo, :gastos, :entrada, :salida,
    :schema_version, :modelo_id, :extraido_en
)
ON CONFLICT ON CONSTRAINT kid_version_logica_uk DO NOTHING
RETURNING id
"""


@dataclass(frozen=True, slots=True)
class ResultadoCarga:
    documento_id: int
    kid_version_id: int | None  # None si ya existía (carga repetida)

    @property
    def insertado(self) -> bool:
        return self.kid_version_id is not None


class RepositorioKids:
    def __init__(self, ejecutor: EjecutorSQL) -> None:
        self._sql = ejecutor

    def documento_cargado(self, sha256: str) -> bool:
        return bool(self._sql.ejecutar(SQL_DOCUMENTO_CARGADO, {"sha256": sha256}))

    def guardar(
        self, resultado: ResultadoExtraccion, json_s3_key: str
    ) -> ResultadoCarga:
        if resultado.estado is not Estado.VALID or resultado.datos is None:
            raise ValueError("Solo se cargan en Aurora las extracciones VALID")
        datos, origen = resultado.datos, resultado.source
        # Garantizados por la validación (campos obligatorios).
        assert datos.isin and datos.nombre_producto and datos.gestora and datos.sri

        with self._sql.transaccion():
            self._sql.ejecutar(
                SQL_GESTORA, {"codigo": origen.gestora, "nombre": datos.gestora}
            )
            fondo_id = self._sql.ejecutar(
                SQL_FONDO,
                {"gestora": origen.gestora, "nombre_producto": datos.nombre_producto},
            )[0]["id"]
            self._sql.ejecutar(SQL_CLASE, {"isin": datos.isin, "fondo_id": fondo_id})
            self._sql.ejecutar(
                SQL_DOCUMENTO,
                {
                    "sha256": origen.pdf_sha256,
                    "gestora": origen.gestora,
                    "tipo_documento": origen.tipo_documento,
                    "s3_bucket": origen.pdf_bucket,
                    "s3_key": origen.pdf_key,
                    "s3_version_id": origen.pdf_version_id,
                    "url_origen": origen.url_origen,
                    "fecha_descarga": origen.fecha_descarga,
                    "correlation_id": origen.correlation_id,
                    "json_s3_key": json_s3_key,
                },
            )
            documento_id = self._sql.ejecutar(
                SQL_ID_DOCUMENTO, {"sha256": origen.pdf_sha256}
            )[0]["id"]
            filas = self._sql.ejecutar(
                SQL_KID_VERSION,
                {
                    "documento_id": documento_id,
                    "isin": datos.isin,
                    "nombre_producto": datos.nombre_producto,
                    "nombre_clase": datos.nombre_clase,
                    "gestora_productor": datos.gestora,
                    "fecha_documento": datos.fecha_documento,
                    "sri": datos.sri,
                    "periodo": datos.periodo_mantenimiento_anios,
                    "gastos": datos.gastos_corrientes_pct,
                    "entrada": datos.costes_entrada_pct,
                    "salida": datos.costes_salida_pct,
                    "schema_version": resultado.schema_version,
                    "modelo_id": resultado.modelo.model_id
                    if resultado.modelo
                    else "desconocido",
                    "extraido_en": resultado.finalizado_en,
                },
            )
        return ResultadoCarga(
            documento_id=documento_id, kid_version_id=filas[0]["id"] if filas else None
        )
