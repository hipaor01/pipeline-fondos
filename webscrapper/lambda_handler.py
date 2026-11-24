"""Adaptador Lambda para las tres gestoras de captura."""

import argparse
import os
from uuid import uuid4

from webscrapper import ingesta
from webscrapper.descargar_kids_azvalor import BASE_URL as AZVALOR_URL
from webscrapper.descargar_kids_azvalor import ScraperAzvalor
from webscrapper.descargar_kids_bestinver import BASE_URL as BESTINVER_URL
from webscrapper.descargar_kids_bestinver import ScraperBestinver
from webscrapper.descargar_kids_cobas import BASE_URL as COBAS_URL
from webscrapper.descargar_kids_cobas import ScraperCobas

GESTORAS = {
    "bestinver": (ScraperBestinver, BESTINVER_URL),
    "azvalor": (ScraperAzvalor, AZVALOR_URL),
    "cobas": (ScraperCobas, COBAS_URL),
}


def handler(event: dict, context) -> dict:
    gestora = os.environ["GESTORA"]
    scraper, url = GESTORAS[gestora]
    bucket = os.environ["BUCKET_DOCUMENTOS"]
    correlation_id = event.get("correlation_id") or str(uuid4())
    if (
        not isinstance(correlation_id, str)
        or len(correlation_id) > 128
        or not correlation_id.isascii()
        or not correlation_id.isprintable()
    ):
        raise ValueError(
            "correlation_id debe ser ASCII imprimible de hasta 128 caracteres"
        )
    args = argparse.Namespace(bucket=bucket, prefijo=gestora, fecha=None, delay=1.0)
    token = ingesta.CORRELATION_ID.set(correlation_id)
    try:
        resultado = ingesta.ejecutar(args, scraper, gestora, url)
    finally:
        ingesta.CORRELATION_ID.reset(token)
    return {
        "gestora": gestora,
        "correlation_id": correlation_id,
        "estado": resultado.estado,
        "subidos": len(resultado.subidos),
        "ausentes": len(resultado.ausentes),
        "fallos": len(resultado.fallos),
    }
