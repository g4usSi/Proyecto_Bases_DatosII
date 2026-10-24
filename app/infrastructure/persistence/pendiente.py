"""Piezas provisionales para operaciones que un motor todavia no implementa.

Reemplazar en cada rama de motor. Mientras existan, la API responde 501 con un
mensaje que indica el motor y la operacion faltante.
"""

from datetime import datetime
from typing import NoReturn

from app.application.errores import OperacionPendiente
from app.domain.cita import Cita, EstadoCita, NuevaCita
from app.domain.consulta import Consulta, NuevaConsulta
from app.domain.odontograma import EstadoPieza, Odontograma
from app.domain.profesional import ProfesionalLocal


def pendiente(motor: str, operacion: str) -> NoReturn:
    raise OperacionPendiente(f"{motor}: '{operacion}' todavia no esta implementado.")


class HistorialPendiente:
    """Implementa RepositorioHistorial lanzando OperacionPendiente."""

    def __init__(self, motor: str) -> None:
        self.motor = motor

    def listar_consultas(
        self, id_paciente: str, limite: int, antes_de: datetime | None = None
    ) -> list[Consulta]:
        pendiente(self.motor, "consultar historial")

    def registrar_consulta(
        self, id_paciente: str, id_profesional: str, datos: NuevaConsulta
    ) -> Consulta:
        pendiente(self.motor, "registrar consulta")


class ProfesionalesPendiente:
    def __init__(self, motor: str) -> None:
        self.motor = motor

    def obtener(self, id_profesional: str) -> ProfesionalLocal | None:
        pendiente(self.motor, "perfil de profesionales")


class CitasPendiente:
    def __init__(self, motor: str) -> None:
        self.motor = motor

    def obtener(self, id_cita: str) -> Cita | None:
        pendiente(self.motor, "citas")

    def agendar(self, datos: NuevaCita, nombre_paciente: str, creada_por: str) -> Cita:
        pendiente(self.motor, "agendar cita")

    def listar_agenda(
        self, desde: datetime, hasta: datetime, id_profesional: str | None = None
    ) -> list[Cita]:
        pendiente(self.motor, "agenda de citas")

    def listar_por_paciente(self, id_paciente: str, limite: int) -> list[Cita]:
        pendiente(self.motor, "citas del paciente")

    def cambiar_estado(
        self, id_cita: str, estado: EstadoCita, por: str, motivo: str | None
    ) -> Cita:
        pendiente(self.motor, "cambiar estado de cita")


class OdontogramaNoAplica:
    """El odontograma es propio de la clinica odontologica."""

    def __init__(self, motor: str) -> None:
        self.motor = motor

    def obtener(self, id_paciente: str) -> Odontograma:
        pendiente(self.motor, "odontograma (solo aplica a la clinica odontologica)")

    def actualizar_pieza(self, id_paciente: str, estado: EstadoPieza) -> None:
        pendiente(self.motor, "odontograma (solo aplica a la clinica odontologica)")


def repositorios_pendientes(motor: str) -> dict[str, object]:
    """Atributos que una unidad de trabajo sin implementacion propia debe exponer."""
    return {
        "historial": HistorialPendiente(motor),
        "profesionales": ProfesionalesPendiente(motor),
        "citas": CitasPendiente(motor),
        "odontograma": OdontogramaNoAplica(motor),
    }
