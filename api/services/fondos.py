"""Casos de uso de consulta de gestoras, fondos y documentos KID."""

from typing import TypeVar

from api.models.common import Isin, ModeloAPI, Paginacion, RespuestaPaginada
from api.models.fondo import FondoDetalle, RespuestaFondos
from api.models.gestora import RespuestaGestoras
from api.models.kid import RespuestaKids
from api.repositories.base import (
    ConsultaPaginada,
    FiltrosFondos,
    FiltrosKids,
    RepositorioFondos,
    ResultadoPaginado,
)
from api.services.errors import FondoNoEncontrado

ModeloT = TypeVar("ModeloT", bound=ModeloAPI)
RespuestaT = TypeVar("RespuestaT", bound=RespuestaPaginada)


class ServicioFondos:
    """Coordina las consultas sin depender de la fuente de datos concreta."""

    def __init__(self, repositorio: RepositorioFondos) -> None:
        self._repositorio = repositorio

    def listar_gestoras(
        self,
        paginacion: ConsultaPaginada,
    ) -> RespuestaGestoras:
        resultado = self._repositorio.listar_gestoras(paginacion)
        return self._crear_respuesta(RespuestaGestoras, resultado, paginacion)

    def listar_fondos(
        self,
        filtros: FiltrosFondos,
        paginacion: ConsultaPaginada,
    ) -> RespuestaFondos:
        resultado = self._repositorio.listar_fondos(filtros, paginacion)
        return self._crear_respuesta(RespuestaFondos, resultado, paginacion)

    def obtener_fondo(self, isin: Isin) -> FondoDetalle:
        fondo = self._repositorio.obtener_fondo(isin)
        if fondo is None:
            raise FondoNoEncontrado(isin)
        return fondo

    def listar_kids(
        self,
        filtros: FiltrosKids,
        paginacion: ConsultaPaginada,
    ) -> RespuestaKids:
        resultado = self._repositorio.listar_kids(filtros, paginacion)
        return self._crear_respuesta(RespuestaKids, resultado, paginacion)

    @staticmethod
    def _crear_respuesta(
        tipo_respuesta: type[RespuestaT],
        resultado: ResultadoPaginado[ModeloT],
        paginacion: ConsultaPaginada,
    ) -> RespuestaT:
        return tipo_respuesta.model_validate(
            {
                "datos": resultado.elementos,
                "paginacion": Paginacion(
                    pagina=paginacion.pagina,
                    tamano_pagina=paginacion.tamano_pagina,
                    total=resultado.total,
                ),
            }
        )
