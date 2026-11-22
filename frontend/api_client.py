"""Cliente HTTP tipado utilizado por el frontend Streamlit."""

from dataclasses import dataclass
from datetime import date
from typing import Generic, TypeVar
from uuid import uuid4

import httpx2
from pydantic import BaseModel, ValidationError

from api.models import (
    Error,
    EstadoServicio,
    FondoDetalle,
    RespuestaFondos,
    RespuestaGestoras,
    RespuestaKids,
)

ModeloRespuestaT = TypeVar("ModeloRespuestaT", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ResultadoAPI(Generic[ModeloRespuestaT]):
    """Respuesta validada junto con el identificador de trazabilidad."""

    datos: ModeloRespuestaT
    correlation_id: str


class ErrorClienteAPI(RuntimeError):
    """Error seguro para mostrar cuando la API no puede responder correctamente."""

    def __init__(self, mensaje: str, correlation_id: str | None = None) -> None:
        super().__init__(mensaje)
        self.correlation_id = correlation_id


class ClienteAPI:
    """Encapsula las peticiones del frontend a la API pública."""

    def __init__(
        self,
        base_url: str,
        timeout_segundos: float,
        *,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._cliente = httpx2.Client(
            base_url=base_url,
            timeout=timeout_segundos,
            transport=transport,
        )

    def obtener_estado(self) -> ResultadoAPI[EstadoServicio]:
        """Consulta el estado de la API y valida su contrato de respuesta."""

        return self._get("/health", EstadoServicio)

    def listar_gestoras(
        self,
        *,
        pagina: int = 1,
        tamano_pagina: int = 100,
    ) -> ResultadoAPI[RespuestaGestoras]:
        """Obtiene una página de gestoras para los filtros del frontend."""

        return self._get(
            "/gestoras",
            RespuestaGestoras,
            parametros={"pagina": pagina, "tamano_pagina": tamano_pagina},
        )

    def listar_fondos(
        self,
        *,
        pagina: int = 1,
        tamano_pagina: int = 20,
        gestora: str | None = None,
        isin: str | None = None,
        nombre: str | None = None,
    ) -> ResultadoAPI[RespuestaFondos]:
        """Obtiene una página de fondos aplicando los filtros indicados."""

        parametros: dict[str, str | int] = {
            "pagina": pagina,
            "tamano_pagina": tamano_pagina,
        }
        if gestora:
            parametros["gestora"] = gestora
        if isin:
            parametros["isin"] = isin
        if nombre:
            parametros["nombre"] = nombre

        return self._get("/fondos", RespuestaFondos, parametros=parametros)

    def obtener_fondo(self, isin: str) -> ResultadoAPI[FondoDetalle]:
        """Obtiene el detalle del fondo identificado por su ISIN."""

        return self._get(f"/fondos/{isin}", FondoDetalle)

    def listar_kids(
        self,
        *,
        pagina: int = 1,
        tamano_pagina: int = 100,
        gestora: str | None = None,
        isin: str | None = None,
        fecha: date | None = None,
    ) -> ResultadoAPI[RespuestaKids]:
        """Obtiene versiones de KID aplicando los filtros indicados."""

        parametros: dict[str, str | int] = {
            "pagina": pagina,
            "tamano_pagina": tamano_pagina,
        }
        if gestora:
            parametros["gestora"] = gestora
        if isin:
            parametros["isin"] = isin
        if fecha:
            parametros["fecha"] = fecha.isoformat()

        return self._get("/kids", RespuestaKids, parametros=parametros)

    def cerrar(self) -> None:
        """Libera las conexiones mantenidas por el cliente HTTP."""

        self._cliente.close()

    def _get(
        self,
        ruta: str,
        modelo: type[ModeloRespuestaT],
        *,
        parametros: dict[str, str | int] | None = None,
    ) -> ResultadoAPI[ModeloRespuestaT]:
        """Ejecuta un GET y aplica el tratamiento común de respuestas."""

        correlation_id_enviado = f"streamlit-{uuid4()}"
        try:
            respuesta = self._cliente.get(
                ruta,
                params=parametros,
                headers={"X-Correlation-Id": correlation_id_enviado},
            )
        except httpx2.TimeoutException as error:
            raise ErrorClienteAPI(
                "La API ha tardado demasiado en responder.",
                correlation_id_enviado,
            ) from error
        except httpx2.RequestError as error:
            raise ErrorClienteAPI(
                "No se ha podido conectar con la API.",
                correlation_id_enviado,
            ) from error

        correlation_id = respuesta.headers.get(
            "X-Correlation-Id",
            correlation_id_enviado,
        )
        if not respuesta.is_success:
            raise ErrorClienteAPI(
                self._mensaje_error(respuesta),
                correlation_id,
            )

        try:
            datos = modelo.model_validate(respuesta.json())
        except (ValueError, ValidationError) as error:
            raise ErrorClienteAPI(
                "La API ha devuelto una respuesta con un formato inesperado.",
                correlation_id,
            ) from error

        return ResultadoAPI(datos=datos, correlation_id=correlation_id)

    @staticmethod
    def _mensaje_error(respuesta: httpx2.Response) -> str:
        try:
            error_api = Error.model_validate(respuesta.json())
        except (ValueError, ValidationError):
            return f"La API ha respondido con el estado HTTP {respuesta.status_code}."
        return error_api.mensaje
