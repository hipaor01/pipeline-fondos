"""Comportamiento de P1 ante repeticiones con S3 versionado simulado."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from threading import Lock

from webscrapper.base import Documento
from webscrapper.ingesta import subir_s3


class S3Versionado:
    def __init__(self) -> None:
        self.versiones = []
        self.lock = Lock()

    def put_object(self, **objeto):
        with self.lock:
            version = str(len(self.versiones) + 1)
            self.versiones.append((version, objeto))
            return {"VersionId": version}


def test_repeticion_cambio_y_fecha_conservan_referencias_y_hashes() -> None:
    s3 = S3Versionado()
    documento = Documento("bestinver", "fondo", "kid", "https://ejemplo.test/a.pdf", "Fondo")
    fecha = datetime(2026, 11, 22, tzinfo=timezone.utc)
    clave = "raw/bestinver/20261122/fondo_kid.pdf"

    for destino, contenido in [(clave, b"pdf-a"), (clave, b"pdf-a"), (clave, b"pdf-b"),
                               ("raw/bestinver/20261123/fondo_kid.pdf", b"pdf-a")]:
        subir_s3(s3, "bucket", destino, contenido, documento, fecha)

    assert [version for version, _ in s3.versiones] == ["1", "2", "3", "4"]
    assert [objeto["Metadata"]["sha256"] for _, objeto in s3.versiones] == [
        sha256(b"pdf-a").hexdigest(), sha256(b"pdf-a").hexdigest(),
        sha256(b"pdf-b").hexdigest(), sha256(b"pdf-a").hexdigest(),
    ]
    assert [objeto["Key"] for _, objeto in s3.versiones] == [clave, clave, clave, "raw/bestinver/20261123/fondo_kid.pdf"]


def test_subidas_concurrentes_no_fingen_deduplicacion() -> None:
    s3 = S3Versionado()
    documento = Documento("bestinver", "fondo", "kid", "https://ejemplo.test/a.pdf", "Fondo")
    fecha = datetime(2026, 11, 22, tzinfo=timezone.utc)
    with ThreadPoolExecutor(max_workers=2) as ejecutor:
        versiones = list(ejecutor.map(
            lambda _: subir_s3(s3, "bucket", "raw/bestinver/20261122/fondo_kid.pdf", b"pdf", documento, fecha),
            range(2),
        ))
    assert set(versiones) == {"1", "2"}
    assert len(s3.versiones) == 2
    assert s3.versiones[0][1]["Metadata"]["sha256"] == s3.versiones[1][1]["Metadata"]["sha256"]
