"""Piezas provisionales para operaciones que un motor todavia no implementa.

Reemplazar en cada rama de motor. Mientras existan, la API responde 501 con un
mensaje que indica el motor y la operacion faltante.
"""

from datetime import date, datetime
from typing import NoReturn

from app.application.errores import OperacionPendiente
from app.domain.cita import Cita, EstadoCita, NuevaCita
from app.domain.cobros import Cobro, EstadoCobro, NuevoCargo, NuevoPago, Servicio
from app.domain.consulta import Adenda, Consulta, Diagnostico, NuevaConsulta
from app.domain.hospital import (
    Cama,
    Departamento,
    EstadoCama,
    Ingreso,
    NuevaOrdenMedica,
    NuevoIngreso,
    ResumenHospital,
    TipoIngreso,
)
from app.domain.laboratorio import (
    EstadoOrden,
    NuevaMuestra,
    Orden,
    PruebaCatalogo,
    Resultado,
    ResumenOrden,
    VersionPrueba,
)
from app.domain.odontograma import EstadoPieza, Odontograma
from app.domain.pediatria import (
    ControlCrecimiento,
    DosisVacuna,
    NuevoControl,
    TipoVacuna,
)
from app.domain.profesional import ProfesionalLocal
from app.domain.tutores import CambiosTutor, NuevoTutor, Tutor, TutorDePaciente, Vinculo


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

    def versiones(self, codigo: str) -> list[VersionPrueba]:
        self._no()

    def listar_institucion(
        self,
        estados: frozenset[EstadoOrden] | None,
        limite: int,
        antes_de: datetime | None = None,
    ) -> list[ResumenOrden]:
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

    def listar_camas(
        self, id_departamento: int | None = None, estado: EstadoCama | None = None
    ) -> list[Cama]:
        self._no()

    def obtener_cama(self, id_cama: int) -> Cama | None:
        self._no()

    def cambiar_estado_cama(self, id_cama: int, estado: EstadoCama) -> Cama:
        self._no()

    def ingresar(
        self, id_paciente: str, id_profesional: str, datos: NuevoIngreso, ahora: datetime
    ) -> Ingreso:
        self._no()

    def obtener_ingreso(self, id_paciente: str, id_ingreso: str) -> Ingreso | None:
        self._no()

    def listar_ingresos(
        self,
        id_paciente: str | None = None,
        abiertos: bool | None = None,
        tipo: TipoIngreso | None = None,
        limite: int = 100,
    ) -> list[Ingreso]:
        self._no()

    def agregar_diagnostico(
        self, id_paciente: str, id_ingreso: str, diagnostico: Diagnostico
    ) -> Ingreso:
        self._no()

    def agregar_orden(
        self,
        id_paciente: str,
        id_ingreso: str,
        id_profesional: str,
        orden: NuevaOrdenMedica,
        ahora: datetime,
    ) -> Ingreso:
        self._no()

    def dar_alta(self, id_paciente: str, id_ingreso: str, motivo: str, ahora: datetime) -> Ingreso:
        self._no()

    def resumen(self, hoy: date) -> ResumenHospital:
        self._no()


class CobrosNoAplica:
    """Cobros y pagos: Hospital General y Centro Pediatrico."""

    def __init__(self, motor: str, operacion: str = "cobros y pagos") -> None:
        self.motor = motor
        self.operacion = operacion

    def _no(self) -> NoReturn:
        pendiente(
            self.motor,
            self.operacion + " (solo aplica al Hospital General y al Centro Pediatrico)",
        )

    def listar_servicios(self) -> list[Servicio]:
        self._no()

    def abrir(
        self,
        id_paciente: str,
        id_atencion: str,
        descripcion: str | None,
        ahora: datetime,
        id_tutor: str | None = None,
    ) -> Cobro:
        self._no()

    def obtener(self, id_paciente: str, id_cobro: str) -> Cobro | None:
        self._no()

    def listar(
        self,
        id_paciente: str | None = None,
        estados: frozenset[EstadoCobro] | None = None,
        limite: int = 100,
    ) -> list[Cobro]:
        self._no()

    def agregar_cargo(
        self, id_paciente: str, id_cobro: str, cargo: NuevoCargo, ahora: datetime
    ) -> Cobro:
        self._no()

    def registrar_pago(
        self, id_paciente: str, id_cobro: str, pago: NuevoPago, ahora: datetime
    ) -> Cobro:
        self._no()

    def anular_pago(self, id_paciente: str, id_cobro: str, id_pago: str) -> Cobro:
        self._no()

    def cerrar(self, id_paciente: str, id_cobro: str, ahora: datetime) -> Cobro:
        self._no()

    def anular(self, id_paciente: str, id_cobro: str, ahora: datetime) -> Cobro:
        self._no()


class TutoresNoAplica:
    """Los tutores del paciente son propios del Centro Pediatrico."""

    def __init__(self, motor: str) -> None:
        self.motor = motor

    def _no(self) -> NoReturn:
        pendiente(self.motor, "tutores del paciente" + _SOLO_PEDIATRIA)

    def listar(self, id_paciente: str) -> list[TutorDePaciente]:
        self._no()

    def buscar_por_documento(self, documento: str) -> Tutor | None:
        self._no()

    def vincular(
        self,
        id_paciente: str,
        vinculo: Vinculo,
        id_tutor: str | None = None,
        nuevo: NuevoTutor | None = None,
    ) -> TutorDePaciente:
        self._no()

    def cambiar(self, id_paciente: str, id_tutor: str, cambios: CambiosTutor) -> TutorDePaciente:
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
        "cobros": CobrosNoAplica(motor),
        "tutores": TutoresNoAplica(motor),
    }
