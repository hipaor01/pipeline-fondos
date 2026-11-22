"""Errores de negocio producidos por la capa de servicio."""

from api.models.common import Isin


class FondoNoEncontrado(LookupError):
    """El ISIN consultado no corresponde a ningún fondo disponible."""

    codigo = "FONDO_NO_ENCONTRADO"

    def __init__(self, isin: Isin) -> None:
        self.isin = isin
        super().__init__(f"No existe ningún fondo con el ISIN {isin}.")
