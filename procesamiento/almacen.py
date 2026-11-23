"""Lectura y escritura en S3 con los metadatos de los contratos C1/C2."""

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ObjetoLeido:
    contenido: bytes
    metadatos: dict[str, str]  # claves normalizadas: minúsculas y con guiones
    version_id: str | None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.contenido).hexdigest()


def normalizar_metadatos(metadatos: dict[str, str]) -> dict[str, str]:
    """C1 usa nombres con guion bajo (tipo_documento); S3 suele llevar guiones. Se aceptan ambos."""
    return {
        clave.lower().replace("_", "-"): valor for clave, valor in metadatos.items()
    }


class AlmacenS3:
    def __init__(self, cliente: Any = None) -> None:
        if cliente is None:
            import boto3

            cliente = boto3.client("s3")
        self._s3 = cliente

    def leer(
        self, bucket: str, clave: str, version_id: str | None = None
    ) -> ObjetoLeido:
        argumentos = {"Bucket": bucket, "Key": clave}
        if version_id:
            argumentos["VersionId"] = version_id
        respuesta = self._s3.get_object(**argumentos)
        return ObjetoLeido(
            contenido=respuesta["Body"].read(),
            metadatos=normalizar_metadatos(respuesta.get("Metadata", {})),
            version_id=respuesta.get("VersionId"),
        )

    def metadatos(self, bucket: str, clave: str) -> dict[str, str] | None:
        """Metadatos del objeto o None si no existe."""
        try:
            respuesta = self._s3.head_object(Bucket=bucket, Key=clave)
        except Exception as error:
            codigo = getattr(error, "response", {}).get("Error", {}).get("Code")
            if codigo in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return normalizar_metadatos(respuesta.get("Metadata", {}))

    def escribir(
        self,
        bucket: str,
        clave: str,
        contenido: bytes,
        tipo_contenido: str,
        metadatos: dict[str, str | None],
    ) -> str | None:
        """Sube el objeto y devuelve su VersionId (si el bucket tiene versionado)."""
        respuesta = self._s3.put_object(
            Bucket=bucket,
            Key=clave,
            Body=contenido,
            ContentType=tipo_contenido,
            Metadata={k: _ascii(v) for k, v in metadatos.items() if v is not None},
        )
        return respuesta.get("VersionId")


def _ascii(valor: str) -> str:
    # Los metadatos de usuario de S3 solo admiten ASCII en la práctica.
    return valor.encode("ascii", "backslashreplace").decode("ascii")
