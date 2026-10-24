"""Atencion clinica comun: consulta + diagnosticos + tratamientos + recetas.

Los nombres de campos siguen la coleccion `consultas` del laboratorio (MongoDB),
documentada como contrato comun de los cuatro establecimientos. Una consulta con
sus diagnosticos, tratamientos y recetas se guarda como UNA operacion atomica:
no puede quedar un diagnostico a medias.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Diagnostico:
    descripcion: str
    codigo: str | None = None  # p. ej. codigo CIE-10, si el equipo decide usarlo
    sistema_codigo: str | None = None  # p. ej. "CIE-10"


@dataclass(frozen=True, slots=True)
class Tratamiento:
    descripcion: str


@dataclass(frozen=True, slots=True)
class Receta:
    medicamento: str
    dosis: str
    frecuencia: str
    via_administracion: str | None = None
    duracion_dias: int | None = None
    instrucciones: str | None = None


@dataclass(frozen=True, slots=True)
class NuevaConsulta:
    motivo: str
    notas: str | None = None
    diagnosticos: tuple[Diagnostico, ...] = field(default_factory=tuple)
    tratamientos: tuple[Tratamiento, ...] = field(default_factory=tuple)
    recetas: tuple[Receta, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Consulta:
    id_consulta: str
    id_paciente: str
    id_profesional: str
    fecha_hora: datetime
    motivo: str
    notas: str | None = None
    diagnosticos: tuple[Diagnostico, ...] = field(default_factory=tuple)
    tratamientos: tuple[Tratamiento, ...] = field(default_factory=tuple)
    recetas: tuple[Receta, ...] = field(default_factory=tuple)
