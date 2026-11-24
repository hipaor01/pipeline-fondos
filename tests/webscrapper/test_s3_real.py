"""Prueba optativa de versiones S3 reales en un bucket de pruebas explícito."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4

import boto3
import pytest

from webscrapper.base import Documento
from webscrapper.ingesta import subir_s3


@pytest.mark.skipif(not os.getenv("P1_TEST_BUCKET"), reason="P1_TEST_BUCKET no configurado")
def test_versiones_repeticion_cambio_fecha_y_concurrencia() -> None:
    bucket = os.environ["P1_TEST_BUCKET"]
    s3 = boto3.client("s3")
    assert s3.get_bucket_versioning(Bucket=bucket)["Status"] == "Enabled"
    prefix = f"raw/p1-test-versiones/{uuid4().hex}/"
    key = f"{prefix}20261124/fondo_kid.pdf"
    other_day = f"{prefix}20261125/fondo_kid.pdf"
    doc = Documento("bestinver", "fondo", "kid", "https://example.test/fondo.pdf", "Fondo")
    now = datetime.now(timezone.utc)
    a, b = b"%PDF-1.4\nprueba-a\n", b"%PDF-1.4\nprueba-b\n"
    try:
        versions = [(key, subir_s3(s3, bucket, key, data, doc, now), data) for data in (a, a, b)]
        versions.append((other_day, subir_s3(s3, bucket, other_day, a, doc, now), a))
        with ThreadPoolExecutor(max_workers=2) as executor:
            concurrent = list(executor.map(lambda _: subir_s3(s3, bucket, key, a, doc, now), range(2)))
        versions.extend((key, version, a) for version in concurrent)
        assert len({version for _, version, _ in versions}) == 6
        assert all(version and version != "null" for _, version, _ in versions)
        for object_key, version, expected in versions:
            obj = s3.get_object(Bucket=bucket, Key=object_key, VersionId=version)
            assert obj["Body"].read() == expected
            assert obj["ContentType"] == "application/pdf"
            assert obj["Metadata"]["sha256"] == sha256(expected).hexdigest()
            assert obj["Metadata"]["tipo-documento"] == "kid"
        assert len({sha256(data).hexdigest() for _, _, data in versions}) == 2
    finally:
        # El prefijo aleatorio pertenece exclusivamente a esta ejecución; eliminar solo sus versiones.
        pages = s3.get_paginator("list_object_versions").paginate(Bucket=bucket, Prefix=prefix)
        for page in pages:
            for item in page.get("Versions", []) + page.get("DeleteMarkers", []):
                s3.delete_object(Bucket=bucket, Key=item["Key"], VersionId=item["VersionId"])
