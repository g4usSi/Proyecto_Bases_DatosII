"""Odontograma con numeracion FDI (ISO 3950).

Permanentes: cuadrantes 1-4, piezas 1-8 (11..48).
Temporales: cuadrantes 5-8, piezas 1-5 (51..85).
El estado de cada pieza sale de una lista fija (EstadoDental), decision del equipo:
el frontend dibuja el odontograma con un color por estado y la API rechaza cualquier
otro valor. Para agregar un estado basta con sumarlo al enum.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

PIEZAS_FDI = frozenset(
    {f"{c}{p}" for c in "1234" for p in "12345678"} | {f"{c}{p}" for c in "5678" for p in "12345"}
)


class EstadoDental(StrEnum):
    """Lista fija de estados de una pieza. El valor es el que viaja por la API."""

    SANA = "sana"
    CARIES = "caries"
    OBTURADA = "obturada"
    CORONA = "corona"
    ENDODONCIA = "endodoncia"
    SELLANTE = "sellante"
    FRACTURA = "fractura"
    PROTESIS = "protesis"
    IMPLANTE = "implante"
    EXTRACCION_INDICADA = "extraccion_indicada"
    AUSENTE = "ausente"
    EN_ERUPCION = "en_erupcion"


class Superficie(StrEnum):
    OCLUSAL = "oclusal"
    INCISAL = "incisal"
    MESIAL = "mesial"
    DISTAL = "distal"
    VESTIBULAR = "vestibular"
    LINGUAL = "lingual"
    PALATINO = "palatino"


def es_pieza_valida(codigo: str) -> bool:
    return codigo in PIEZAS_FDI


@dataclass(frozen=True, slots=True)
class EstadoPieza:
    pieza: str
    estado: EstadoDental
    actualizado_por: str
    actualizado_en: datetime
    superficies: tuple[Superficie, ...] = field(default_factory=tuple)
    nota: str | None = None


@dataclass(frozen=True, slots=True)
class Odontograma:
    id_paciente: str
    piezas: dict[str, EstadoPieza]
