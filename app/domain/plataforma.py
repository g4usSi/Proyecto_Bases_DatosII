"""Resumen de la plataforma para el superusuario: SOLO conteos por entidad.

Nunca incluye nombres, ids ni datos de pacientes. Cada numero sale del motor de su entidad
(PostgreSQL, MySQL, MongoDB o Firestore); si un motor no responde, esa entidad se devuelve
sin indicadores y el resto del resumen sigue siendo valido.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.domain.institucion import Institucion


@dataclass(frozen=True, slots=True)
class IndicadoresEntidad:
    """Lo que cuenta el motor de una entidad. None = no aplica a esa entidad."""

    pacientes_registrados: int
    citas_hoy: int | None = None
    citas_semana: int | None = None
    # Hospital General
    camas_ocupadas: int | None = None
    camas_total: int | None = None
    emergencias_activas: int | None = None
    # Hospital General (cobros abiertos o cerrados) y Centro Pediatrico (facturas por cobrar)
    cobros_por_cobrar: int | None = None
    saldo_por_cobrar: Decimal | None = None
    # Laboratorio Clinico
    ordenes_abiertas: int | None = None


@dataclass(frozen=True, slots=True)
class ResumenEntidad:
    institucion: Institucion
    administrador: str | None  # nombre del administrador activo
    personal_activo: int
    personal_sin_acceso: int  # bloqueadas o deshabilitadas
    indicadores: IndicadoresEntidad | None  # None: el motor no respondio


@dataclass(frozen=True, slots=True)
class ResumenPlataforma:
    entidades: tuple[ResumenEntidad, ...]
