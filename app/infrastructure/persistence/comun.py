"""Utilidades compartidas por los adaptadores SQL."""

from datetime import UTC, datetime

ENTERO_MAXIMO = 2_147_483_647


def entero_positivo(identificador: str) -> int | None:
    """Los identificadores SQL son enteros positivos de 32 bits; todo lo demas no existe."""
    if not identificador.isascii() or not identificador.isdecimal():
        return None
    numero = int(identificador)
    return numero if 0 < numero <= ENTERO_MAXIMO else None


def escapar_like(texto: str) -> str:
    """Convierte % _ y \\ en texto literal dentro de un LIKE."""
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def utc_ingenuo(valor: datetime) -> datetime:
    """Las columnas TIMESTAMP/DATETIME guardan UTC sin zona; asi no dependen del servidor."""
    if valor.tzinfo is None:
        return valor
    return valor.astimezone(UTC).replace(tzinfo=None)


def con_utc(valor: datetime) -> datetime:
    return valor.replace(tzinfo=UTC) if valor.tzinfo is None else valor.astimezone(UTC)
