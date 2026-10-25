"""Hospital General: infraestructura (departamentos, camas) e ingresos hospitalarios.

En el modelo del hospital todo encuentro clinico es una "atencion":
- CONSULTA: la consulta comun de los cuatro motores (historial);
- INGRESO: el paciente ocupa una cama (emergencia, programado o traslado) hasta el alta.
Durante un ingreso se agregan diagnosticos y ordenes medicas (medicamento con receta,
examen, procedimiento o interconsulta). Nada se borra: un error se aclara con otro registro.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain.consulta import Diagnostico, Receta
from app.domain.errores import DatosInvalidos


class EstadoCama(StrEnum):
    DISPONIBLE = "disponible"
    OCUPADA = "ocupada"  # solo la pone un ingreso; la quita el alta
    LIMPIEZA = "limpieza"
    MANTENIMIENTO = "mantenimiento"


# Estados que el personal puede poner a mano (ocupada no: depende de los ingresos).
ESTADOS_CAMA_MANUALES = frozenset(
    {EstadoCama.DISPONIBLE, EstadoCama.LIMPIEZA, EstadoCama.MANTENIMIENTO}
)


class TipoIngreso(StrEnum):
    EMERGENCIA = "emergencia"
    PROGRAMADO = "programado"
    TRASLADO = "traslado"


class TipoOrdenMedica(StrEnum):
    MEDICAMENTO = "medicamento"
    EXAMEN = "examen"
    PROCEDIMIENTO = "procedimiento"
    INTERCONSULTA = "interconsulta"


@dataclass(frozen=True, slots=True)
class Departamento:
    id_departamento: int
    nombre: str
    habitaciones: int = 0
    camas: int = 0
    camas_disponibles: int = 0


@dataclass(frozen=True, slots=True)
class OcupanteCama:
    id_ingreso: str
    id_paciente: str
    nombre_paciente: str
    tipo: TipoIngreso
    desde: datetime


@dataclass(frozen=True, slots=True)
class Cama:
    id_cama: int
    codigo: str
    id_habitacion: int
    habitacion: str
    id_departamento: int
    departamento: str
    estado: EstadoCama
    ocupante: OcupanteCama | None = None


@dataclass(frozen=True, slots=True)
class OrdenMedica:
    id_orden: str
    tipo: TipoOrdenMedica
    fecha_hora: datetime
    id_profesional: str
    descripcion: str | None = None
    recetas: tuple[Receta, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class NuevaOrdenMedica:
    tipo: TipoOrdenMedica
    descripcion: str | None = None
    recetas: tuple[Receta, ...] = field(default_factory=tuple)

    def validar(self) -> None:
        if self.tipo == TipoOrdenMedica.MEDICAMENTO:
            if not self.recetas:
                raise DatosInvalidos("Una orden de medicamento necesita al menos una receta.")
        else:
            if self.recetas:
                raise DatosInvalidos("Solo las ordenes de medicamento llevan recetas.")
            if not (self.descripcion or "").strip():
                raise DatosInvalidos("Describe que se solicita (examen, procedimiento, etc.).")


@dataclass(frozen=True, slots=True)
class NuevoIngreso:
    id_cama: int
    tipo: TipoIngreso
    motivo: str
    diagnosticos: tuple[Diagnostico, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Ingreso:
    id_ingreso: str  # id de la atencion de tipo INGRESO
    id_paciente: str
    nombre_paciente: str
    id_profesional: str
    tipo: TipoIngreso
    motivo: str
    id_cama: int
    cama: str
    departamento: str
    ingreso_en: datetime
    alta_en: datetime | None = None
    motivo_alta: str | None = None
    diagnosticos: tuple[Diagnostico, ...] = field(default_factory=tuple)
    ordenes: tuple[OrdenMedica, ...] = field(default_factory=tuple)

    @property
    def abierto(self) -> bool:
        return self.alta_en is None


@dataclass(frozen=True, slots=True)
class ResumenHospital:
    """Tablero de inicio: conteos, sin datos de pacientes."""

    camas_por_estado: dict[str, int]
    ingresos_abiertos: int
    emergencias_abiertas: int
    ingresos_hoy: int
    altas_hoy: int
    citas_hoy_por_estado: dict[str, int]

    @property
    def camas_total(self) -> int:
        return sum(self.camas_por_estado.values())

    @property
    def ocupacion(self) -> float:
        """Porcentaje de camas ocupadas (0-100)."""
        total = self.camas_total
        return (
            round(100 * self.camas_por_estado.get(EstadoCama.OCUPADA, 0) / total, 1)
            if total
            else 0.0
        )
