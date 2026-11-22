"""Implementación en memoria del repositorio de consulta de fondos."""

from collections.abc import Callable, Iterable, Sequence
from typing import Self, TypeVar

from pydantic import BaseModel

from api.models.common import Isin
from api.models.fondo import FondoDetalle, FondoResumen
from api.models.gestora import Gestora
from api.models.kid import KidVersion
from api.repositories.base import (
    ConsultaPaginada,
    FiltrosFondos,
    FiltrosKids,
    RepositorioFondos,
    ResultadoPaginado,
)

ElementoT = TypeVar("ElementoT")
ModeloT = TypeVar("ModeloT", bound=BaseModel)


class RepositorioFondosEnMemoria(RepositorioFondos):
    """Repositorio determinista para desarrollo y pruebas sin Aurora."""

    def __init__(
        self,
        gestoras: Iterable[Gestora],
        fondos: Iterable[FondoDetalle],
        kids: Iterable[KidVersion],
    ) -> None:
        gestoras_copiadas = tuple(self._copiar_modelo(gestora) for gestora in gestoras)
        fondos_copiados = tuple(self._copiar_modelo(fondo) for fondo in fondos)
        kids_copiados = tuple(self._copiar_modelo(kid) for kid in kids)

        self._gestoras = self._indexar_unicos(
            gestoras_copiadas,
            clave=lambda gestora: gestora.codigo,
            descripcion="código de gestora",
        )
        self._fondos = self._indexar_unicos(
            fondos_copiados,
            clave=lambda fondo: fondo.isin,
            descripcion="ISIN de fondo",
        )
        self._asegurar_unicos(
            kids_copiados,
            clave=lambda kid: kid.documento_sha256,
            descripcion="SHA-256 de documento KID",
        )
        self._validar_referencias(fondos_copiados, kids_copiados)
        self._kids = kids_copiados

    @classmethod
    def con_datos_semilla(cls) -> Self:
        """Construye un repositorio nuevo con datos deterministas de demostración."""

        from api.repositories.seed import crear_datos_semilla

        gestoras, fondos, kids = crear_datos_semilla()
        return cls(gestoras=gestoras, fondos=fondos, kids=kids)

    def listar_gestoras(
        self,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[Gestora]:
        gestoras = sorted(
            self._gestoras.values(),
            key=lambda gestora: (gestora.nombre.casefold(), gestora.codigo),
        )
        return self._paginar(gestoras, paginacion)

    def listar_fondos(
        self,
        filtros: FiltrosFondos,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[FondoResumen]:
        fondos = (
            self._a_resumen(fondo)
            for fondo in self._fondos.values()
            if self._cumple_filtros_fondo(fondo, filtros)
        )
        fondos_ordenados = sorted(
            fondos,
            key=lambda fondo: (fondo.nombre_producto.casefold(), fondo.isin),
        )
        return self._paginar(fondos_ordenados, paginacion)

    def obtener_fondo(self, isin: Isin) -> FondoDetalle | None:
        fondo = self._fondos.get(isin)
        return self._copiar_modelo(fondo) if fondo is not None else None

    def listar_kids(
        self,
        filtros: FiltrosKids,
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[KidVersion]:
        kids = (kid for kid in self._kids if self._cumple_filtros_kid(kid, filtros))
        kids_ordenados = sorted(kids, key=self._clave_orden_kid)
        return self._paginar(kids_ordenados, paginacion)

    def _validar_referencias(
        self,
        fondos: Sequence[FondoDetalle],
        kids: Sequence[KidVersion],
    ) -> None:
        for fondo in fondos:
            gestora = self._gestoras.get(fondo.gestora.codigo)
            if gestora != fondo.gestora:
                raise ValueError(
                    f"La gestora del fondo {fondo.isin} no existe o no coincide."
                )

        for kid in kids:
            fondo_asociado = self._fondos.get(kid.isin)
            if fondo_asociado is None:
                raise ValueError(
                    f"El KID {kid.documento_sha256} no tiene fondo asociado."
                )
            if fondo_asociado.gestora != kid.gestora:
                raise ValueError(
                    f"La gestora del KID {kid.documento_sha256} no coincide con su fondo."
                )

    @staticmethod
    def _cumple_filtros_fondo(
        fondo: FondoDetalle,
        filtros: FiltrosFondos,
    ) -> bool:
        if filtros.gestora is not None and fondo.gestora.codigo != filtros.gestora:
            return False
        if filtros.isin is not None and fondo.isin != filtros.isin:
            return False
        if (
            filtros.nombre is not None
            and filtros.nombre.casefold() not in fondo.nombre_producto.casefold()
        ):
            return False
        return True

    @staticmethod
    def _cumple_filtros_kid(kid: KidVersion, filtros: FiltrosKids) -> bool:
        if filtros.gestora is not None and kid.gestora.codigo != filtros.gestora:
            return False
        if filtros.isin is not None and kid.isin != filtros.isin:
            return False
        if (
            filtros.fecha_documento is not None
            and kid.fecha_documento != filtros.fecha_documento
        ):
            return False
        return True

    @staticmethod
    def _clave_orden_kid(kid: KidVersion) -> tuple[bool, int, str, str]:
        fecha_ordinal = kid.fecha_documento.toordinal() if kid.fecha_documento else 0
        return (
            kid.fecha_documento is None,
            -fecha_ordinal,
            kid.isin,
            kid.documento_sha256,
        )

    @staticmethod
    def _a_resumen(fondo: FondoDetalle) -> FondoResumen:
        campos = set(FondoResumen.model_fields)
        return FondoResumen.model_validate(fondo.model_dump(include=campos))

    @classmethod
    def _paginar(
        cls,
        elementos: Sequence[ModeloT],
        paginacion: ConsultaPaginada,
    ) -> ResultadoPaginado[ModeloT]:
        inicio = paginacion.desplazamiento
        fin = inicio + paginacion.tamano_pagina
        pagina = tuple(
            cls._copiar_modelo(elemento) for elemento in elementos[inicio:fin]
        )
        return ResultadoPaginado(elementos=pagina, total=len(elementos))

    @staticmethod
    def _copiar_modelo(modelo: ModeloT) -> ModeloT:
        return modelo.model_copy(deep=True)

    @staticmethod
    def _indexar_unicos(
        elementos: Sequence[ElementoT],
        clave: Callable[[ElementoT], str],
        descripcion: str,
    ) -> dict[str, ElementoT]:
        RepositorioFondosEnMemoria._asegurar_unicos(elementos, clave, descripcion)
        return {clave(elemento): elemento for elemento in elementos}

    @staticmethod
    def _asegurar_unicos(
        elementos: Sequence[ElementoT],
        clave: Callable[[ElementoT], str],
        descripcion: str,
    ) -> None:
        vistos: set[str] = set()
        for elemento in elementos:
            valor = clave(elemento)
            if valor in vistos:
                descripcion_con_mayuscula = descripcion[:1].upper() + descripcion[1:]
                raise ValueError(f"{descripcion_con_mayuscula} duplicado: {valor}.")
            vistos.add(valor)
