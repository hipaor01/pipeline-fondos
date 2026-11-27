"""Etapa Markdown -> datos KID -> Aurora (contrato C3). Handler: `procesamiento.extraccion.handler`.

SQS (processed/markdown/*.md, batch=1) -> esta Lambda -> Bedrock -> validación
-> JSON de auditoría (siempre) -> upsert en Aurora (solo VALID).

Orden pensado para reintentos seguros:
1. Si ya hay JSON VALID/REJECTED para este PDF (mismo sha256), no se vuelve a llamar
   a Bedrock. Si era VALID, se repite la carga en Aurora (idempotente) por si falló.
2. Si el PDF ya está en Aurora (mismo contenido descargado otro día), se audita
   como VALID duplicado sin llamar a Bedrock.
3. Si no, Bedrock -> validación -> se escribe el JSON -> si es VALID, upsert.

Estados: VALID (se carga), REJECTED (semántico, sin reintento), ERROR (técnico:
se reintenta y, en el último intento, se deja el JSON ERROR antes de ir a la DLQ).
"""

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from procesamiento import eventos, rutas
from procesamiento.almacen import AlmacenS3
from procesamiento.bedrock import ExtractorBedrock
from procesamiento.datos.repositorio import RepositorioKids
from procesamiento.esquema import (
    VERSION_ESQUEMA,
    Estado,
    InfoModelo,
    Origen,
    ResultadoExtraccion,
    Validacion,
)
from procesamiento.observabilidad import Cronometro, log, metrica_resultado
from procesamiento.validacion import validar_extraccion

ETAPA = "extraccion"


@dataclass
class Dependencias:
    almacen: AlmacenS3
    extractor: ExtractorBedrock
    repositorio: RepositorioKids
    tipos_kid: frozenset[str]
    max_intentos: int


def _origen(
    objeto: eventos.ObjetoS3,
    ruta: rutas.RutaDocumento,
    metadatos: dict[str, str],
    version: str | None,
) -> Origen:
    return Origen(
        gestora=metadatos.get("gestora") or ruta.gestora,
        tipo_documento=metadatos.get("tipo-documento") or ruta.tipo_documento,
        url_origen=metadatos.get("url-origen"),
        fecha_descarga=metadatos.get("fecha-descarga-utc")
        or metadatos.get("fecha-descarga"),
        correlation_id=metadatos.get("correlation-id") or "sin-correlation-id",
        pdf_bucket=metadatos.get("pdf-bucket") or objeto.bucket,
        pdf_key=metadatos.get("pdf-key") or ruta.clave_raw,
        pdf_version_id=metadatos.get("pdf-version-id"),
        pdf_sha256=metadatos["pdf-sha256"],
        markdown_bucket=objeto.bucket,
        markdown_key=objeto.clave,
        markdown_version_id=version or objeto.version_id,
        modo_ocr=metadatos.get("modo-ocr"),
        conversor=metadatos.get("conversor"),
    )


def _guardar_json(
    dep: Dependencias, bucket: str, ruta: rutas.RutaDocumento, r: ResultadoExtraccion
) -> None:
    dep.almacen.escribir(
        bucket,
        ruta.clave_estructurada,
        r.model_dump_json(indent=2).encode("utf-8"),
        "application/json",
        {
            "pdf-sha256": r.source.pdf_sha256,
            "estado": r.estado.value,
            "schema-version": r.schema_version,
            "correlation-id": r.source.correlation_id,
        },
    )


def _leer_json_previo(
    dep: Dependencias, bucket: str, ruta: rutas.RutaDocumento, sha256: str
) -> ResultadoExtraccion | None:
    meta = dep.almacen.metadatos(bucket, ruta.clave_estructurada)
    if (
        not meta
        or meta.get("pdf-sha256") != sha256
        or meta.get("estado") not in (Estado.VALID, Estado.REJECTED)
    ):
        return None
    if meta.get("schema-version") != VERSION_ESQUEMA:
        return None  # cambio de esquema: se vuelve a extraer
    previo = dep.almacen.leer(bucket, ruta.clave_estructurada)
    return ResultadoExtraccion.model_validate_json(previo.contenido)


def procesar(objeto: eventos.ObjetoS3, dep: Dependencias, intento: int) -> str:
    cronometro = Cronometro()
    ruta = rutas.desde_clave_markdown(objeto.clave)
    md = dep.almacen.leer(objeto.bucket, objeto.clave, objeto.version_id)
    origen = _origen(objeto, ruta, md.metadatos, md.version_id)
    ctx = {
        "correlation_id": origen.correlation_id,
        "clave": objeto.clave,
        "sha256": origen.pdf_sha256,
    }

    def terminar(r: ResultadoExtraccion, etiqueta: str | None = None) -> str:
        resultado = etiqueta or r.estado.value
        metrica_resultado(
            ETAPA,
            resultado,
            cronometro.ms,
            origen.correlation_id,
            tokens_entrada=r.modelo.tokens_entrada if r.modelo else None,
        )
        log(
            "INFO",
            "Extracción terminada",
            estado=r.estado.value,
            resultado=resultado,
            motivo=r.motivo,
            **ctx,
        )
        return resultado

    # 1. Reintento o reproceso de un documento ya resuelto.
    previo = _leer_json_previo(dep, objeto.bucket, ruta, origen.pdf_sha256)
    if previo:
        if previo.estado is Estado.VALID and not previo.duplicado:
            dep.repositorio.guardar(previo, ruta.clave_estructurada)
        elif previo.estado is Estado.VALID:
            dep.repositorio.registrar_observacion(
                previo.source, ruta.clave_estructurada
            )
        return terminar(previo, f"{previo.estado.value}_PREVIO")

    base: dict[str, Any] = {"source": origen, "iniciado_en": cronometro.inicio_utc}

    # 2. No es un KID (p. ej. ficha del fondo): no se gasta una llamada a Bedrock.
    if origen.tipo_documento not in dep.tipos_kid:
        r = ResultadoExtraccion(
            **base,
            estado=Estado.REJECTED,
            motivo="no_es_kid",
            finalizado_en=datetime.now(UTC),
            validaciones=[
                Validacion(
                    regla="tipo_documento",
                    resultado="fallo",
                    detalle=f"'{origen.tipo_documento}' no está en {sorted(dep.tipos_kid)}",
                )
            ],
        )
        _guardar_json(dep, objeto.bucket, ruta, r)
        return terminar(r)

    # 3. Mismo PDF ya cargado (descargado otro día o reintento de P1): no se llama a
    #    Bedrock, pero se guarda esta observación (procedencia) en Aurora.
    if dep.repositorio.documento_cargado(origen.pdf_sha256):
        dep.repositorio.registrar_observacion(origen, ruta.clave_estructurada)
        r = ResultadoExtraccion(
            **base,
            estado=Estado.VALID,
            duplicado=True,
            finalizado_en=datetime.now(UTC),
            validaciones=[
                Validacion(
                    regla="duplicado",
                    resultado="ok",
                    detalle="sha256 ya cargado en Aurora",
                )
            ],
        )
        _guardar_json(dep, objeto.bucket, ruta, r)
        return terminar(r, "DUPLICADO")

    # 4. Extracción con Bedrock y validación.
    texto = md.contenido.decode("utf-8")
    try:
        respuesta = dep.extractor.extraer(texto)
    except Exception as error:
        if intento >= dep.max_intentos:
            r = ResultadoExtraccion(
                **base,
                estado=Estado.ERROR,
                motivo="error_tecnico",
                errores=[repr(error)],
                modelo=InfoModelo(
                    model_id=dep.extractor.model_id, region=dep.extractor.region
                ),
                finalizado_en=datetime.now(UTC),
            )
            _guardar_json(dep, objeto.bucket, ruta, r)
            terminar(r)
        raise

    validacion = validar_extraccion(respuesta.datos, texto)
    r = ResultadoExtraccion(
        **base,
        estado=validacion.estado,
        motivo=validacion.motivo,
        modelo=InfoModelo(
            model_id=dep.extractor.model_id,
            region=dep.extractor.region,
            latencia_ms=respuesta.latencia_ms,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            stop_reason=respuesta.stop_reason,
        ),
        datos=validacion.datos if validacion.estado is Estado.VALID else None,
        datos_crudos=respuesta.datos,
        evidencias=validacion.evidencias,
        validaciones=validacion.validaciones,
        finalizado_en=datetime.now(UTC),
    )
    _guardar_json(dep, objeto.bucket, ruta, r)
    if r.estado is Estado.VALID:
        carga = dep.repositorio.guardar(r, ruta.clave_estructurada)
        log(
            "INFO",
            "Cargado en Aurora",
            documento_id=carga.documento_id,
            nuevo=carga.insertado,
            **ctx,
        )
    return terminar(r)


def dependencias_desde_entorno() -> Dependencias:
    from database.ejecutor import EjecutorDataAPI

    entorno = os.environ
    return Dependencias(
        almacen=AlmacenS3(),
        extractor=ExtractorBedrock(
            model_id=entorno["BEDROCK_MODEL_ID"],
            region=entorno.get(
                "BEDROCK_REGION", entorno.get("AWS_REGION", "eu-west-3")
            ),
            max_tokens=int(entorno.get("BEDROCK_MAX_TOKENS", "2000")),
        ),
        repositorio=RepositorioKids(
            EjecutorDataAPI(
                entorno["DB_CLUSTER_ARN"],
                entorno["DB_SECRET_ARN"],
                entorno.get("DB_NAME", "fondos"),
            )
        ),
        tipos_kid=frozenset(json.loads(entorno.get("TIPOS_KID", '["kid"]'))),
        max_intentos=int(entorno.get("SQS_MAX_RECEIVE_COUNT", "3")),
    )


_DEPENDENCIAS: Dependencias | None = None  # reutilizadas entre invocaciones en caliente


def handler(
    evento: dict[str, Any],
    contexto: Any = None,
    dependencias: Dependencias | None = None,
) -> dict[str, Any]:
    global _DEPENDENCIAS
    if dependencias is None:
        _DEPENDENCIAS = _DEPENDENCIAS or dependencias_desde_entorno()
        dependencias = _DEPENDENCIAS
    fallos = []
    for mensaje in eventos.leer_registros(evento):
        try:
            for objeto in mensaje.objetos:
                try:
                    procesar(objeto, dependencias, mensaje.intentos)
                except rutas.ClaveNoValida as error:
                    log(
                        "ERROR",
                        "Clave fuera del contrato C2; se descarta",
                        error=str(error),
                        clave=objeto.clave,
                    )
                    metrica_resultado(ETAPA, "REJECTED", 0)
        except Exception as error:
            log(
                "ERROR",
                "Error técnico; SQS reintentará",
                error=repr(error),
                message_id=mensaje.message_id,
                intento=mensaje.intentos,
            )
            metrica_resultado(ETAPA, "FALLO_INTENTO", 0)
            fallos.append({"itemIdentifier": mensaje.message_id})
    return {"batchItemFailures": fallos}
