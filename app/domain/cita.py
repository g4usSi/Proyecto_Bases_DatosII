"""Agenda de citas (Clinica Odontologica; otros motores pueden implementarla despues)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class EstadoCita(StrEnum):
    PROGRAMADA = "programada"
    CONFIRMADA = "confirmada"
    ATENDIDA = "atendida"
    CANCELADA = "cancelada"
    NO_ASISTIO = "no_asistio"


# Una cita sale de "programada" (o de "confirmada") y los estados finales no cambian.
_FINALES = {EstadoCita.ATENDIDA, EstadoCita.CANCELADA, EstadoCita.NO_ASISTIO}
TRANSICIONES = {
    EstadoCita.PROGRAMADA: {EstadoCita.CONFIRMADA} | _FINALES,
    EstadoCita.CONFIRMADA: _FINALES,
}
# Estados que ocupan el horario del profesional (una cita cancelada lo libera).
ESTADOS_OCUPAN_HORARIO = frozenset({EstadoCita.PROGRAMADA, EstadoCita.CONFIRMADA})


@dataclass(frozen=True, slots=True)
class NuevaCita:
    id_paciente: str
    id_profesional: str
    inicio: datetime  # con zona horaria
    duracion_minutos: int
    motivo: str

    @property
    def fin(self) -> datetime:
        return self.inicio + timedelta(minutes=self.duracion_minutos)


@dataclass(frozen=True, slots=True)
class Cita:
    id_cita: str
    id_paciente: str
    nombre_paciente: str  # copia para mostrar la agenda sin leer cada paciente
    id_profesional: str
    inicio: datetime
    fin: datetime
    motivo: str
    estado: EstadoCita
    creada_por: str
    motivo_cambio: str | None = None
