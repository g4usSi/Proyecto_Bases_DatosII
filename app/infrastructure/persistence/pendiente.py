"""Piezas provisionales para operaciones que un motor todavia no implementa.

Reemplazar en cada rama de motor. Mientras existan, la API responde 501 con un
mensaje que indica el motor y la operacion faltante.
"""

from datetime import date, datetime
from typing import NoReturn

from app.application.errores import OperacionPendiente
from app.domain.cita import Cita, EstadoCita, NuevaCita
from app.domain.consulta import Adenda, Consulta, NuevaConsulta
from app.domain.hospital import Departamento
from app.domain.laboratorio import NuevaMuestra, Orden, PruebaCatalogo, Resultado
from app.domain.odontograma import EstadoPieza, Odontograma
from app.domain.pediatria import (
    ControlCrecimiento,
    DosisVacuna,
    NuevoControl,
    TipoVacuna,
)
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

    def obtener_consulta(self, id_paciente: str, id_consulta: str) -> Consulta | None:
        pendiente(self.motor, "consultar una consulta")

    def agregar_a_consulta(
        self, id_paciente: str, id_consulta: str, id_profesional: str, adenda: Adenda
    ) -> Consulta:
        pendiente(self.motor, "agregar a una consulta")


class ProfesionalesPendiente:
    def __init__(self, motor: str) -> None:
        self.motor = motor

    def obtener(self, id_profesional: str) -> ProfesionalLocal | None:
        pendiente(self.motor, "perfil de profesionales")

    def sincronizar(self, perfil: ProfesionalLocal) -> None:
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


_SOLO_PEDIATRIA = " (solo aplica al Centro Pediatrico)"


class CrecimientoNoAplica:
    """Los controles de crecimiento son propios del Centro Pediatrico."""

    def __init__(self, motor: str) -> None:
        self.motor = motor

    def registrar(
        self, id_paciente: str, datos: NuevoControl, fecha: datetime, edad_meses: int | None
    ) -> ControlCrecimiento:
        pendiente(self.motor, "controles de crecimiento" + _SOLO_PEDIATRIA)

    def listar(self, id_paciente: str, limite: int) -> list[ControlCrecimiento]:
        pendiente(self.motor, "controles de crecimiento" + _SOLO_PEDIATRIA)


class VacunacionNoAplica:
    """El esquema de vacunacion es propio del Centro Pediatrico."""

    def __init__(self, motor: str) -> None:
        self.motor = motor

    def _no(self) -> NoReturn:
        pendiente(self.motor, "esquema de vacunacion" + _SOLO_PEDIATRIA)

    def listar_tipos(self) -> list[TipoVacuna]:
        self._no()

    def listar_esquema(self, id_paciente: str) -> list[DosisVacuna]:
        self._no()

    def obtener_dosis(self, id_paciente: str, id_dosis: str) -> DosisVacuna | None:
        self._no()

    def programar(
        self,
        id_paciente: str,
        id_vacuna: str,
        numero_dosis: int | None,
        fecha_programada: date | None,
    ) -> DosisVacuna:
        self._no()

    def aplicar(
        self,
        id_paciente: str,
        id_dosis: str,
        id_profesional: str,
        fecha: datetime,
        observaciones: str | None,
    ) -> DosisVacuna:
        self._no()

    def cancelar(self, id_paciente: str, id_dosis: str) -> DosisVacuna:
        self._no()


class LaboratorioNoAplica:
    """Las ordenes de laboratorio son propias del Laboratorio Clinico."""

    def __init__(self, motor: str) -> None:
        self.motor = motor

    def _no(self) -> NoReturn:
        pendiente(self.motor, "ordenes de laboratorio (solo aplica al Laboratorio Clinico)")

    def listar_catalogo(self) -> list[PruebaCatalogo]:
        self._no()

    def solicitar(
        self, id_paciente: str, id_consulta: str, id_profesional: str, codigos: tuple[str, ...]
    ) -> Orden:
        self._no()

    def obtener(self, id_paciente: str, id_orden: str) -> Orden | None:
        self._no()

    def listar(self, id_paciente: str, limite: int) -> list[Orden]:
        self._no()

    def registrar_muestra(
        self, id_paciente: str, id_orden: str, muestra: NuevaMuestra, ahora: datetime
    ) -> Orden:
        self._no()

    def registrar_resultados(
        self,
        id_paciente: str,
        id_orden: str,
        codigo_prueba: str,
        resultados: tuple[Resultado, ...],
        observaciones: str | None,
        id_profesional: str,
        ahora: datetime,
    ) -> Orden:
        self._no()

    def validar(
        self, id_paciente: str, id_orden: str, id_profesional: str, ahora: datetime
    ) -> Orden:
        self._no()

    def cancelar(
        self, id_paciente: str, id_orden: str, motivo: str, id_profesional: str, ahora: datetime
    ) -> Orden:
        self._no()


class HospitalNoAplica:
    """Departamentos, camas, ingresos y cobros del Hospital General."""

    def __init__(self, motor: str) -> None:
        self.motor = motor

    def _no(self) -> NoReturn:
        pendiente(self.motor, "modulo hospitalario (solo aplica al Hospital General)")

    def listar_departamentos(self) -> list[Departamento]:
        self._no()


def repositorios_pendientes(motor: str) -> dict[str, object]:
    """Atributos que una unidad de trabajo sin implementacion propia debe exponer."""
    return {
        "historial": HistorialPendiente(motor),
        "profesionales": ProfesionalesPendiente(motor),
        "citas": CitasPendiente(motor),
        "odontograma": OdontogramaNoAplica(motor),
        "crecimiento": CrecimientoNoAplica(motor),
        "vacunacion": VacunacionNoAplica(motor),
        "laboratorio": LaboratorioNoAplica(motor),
        "hospital": HospitalNoAplica(motor),
    }
