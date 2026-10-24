"""Agenda de citas (Clinica Odontologica; otros motores pueden implementarla despues)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class EstadoCita(StrEnum):
    PROGRAMADA = "programada"
    ATENDIDA = "atendida"
    CANCELADA = "cancelada"
    NO_ASISTIO = "no_asistio"


# Una cita solo puede salir de "programada"; los estados finales no cambian.
TRANSICIONES = {
    EstadoCita.PROGRAMADA: {EstadoCita.ATENDIDA, EstadoCita.CANCELADA, EstadoCita.NO_ASISTIO},
}


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
