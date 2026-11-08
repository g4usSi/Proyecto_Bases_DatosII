"""Modulo pediatrico (Centro Pediatrico, MySQL): crecimiento y esquema de vacunacion."""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from app.domain.errores import DatosInvalidos

EDAD_MAXIMA_MESES = 216  # el Centro Pediatrico atiende hasta los 18 anos


@dataclass(frozen=True, slots=True)
class NuevoControl:
    """Medidas tomadas en una visita. Los percentiles los aporta quien los calcula."""

    peso_kg: float | None = None
    talla_cm: float | None = None
    perimetro_cefalico: float | None = None
    percentil_peso: float | None = None
    percentil_talla: float | None = None
    referencia_percentiles: str | None = None  # p. ej. "OMS 2006"
    observaciones: str | None = None

    @property
    def vacio(self) -> bool:
        return (
            self.peso_kg is None
            and self.talla_cm is None
            and self.perimetro_cefalico is None
            and not self.observaciones
        )


@dataclass(frozen=True, slots=True)
class ControlCrecimiento:
    id_control: str
    id_paciente: str
    fecha_registro: datetime
    edad_meses: int | None  # edad observada ese dia; no se recalcula despues
    peso_kg: float | None = None
    talla_cm: float | None = None
    perimetro_cefalico: float | None = None
    percentil_peso: float | None = None
    percentil_talla: float | None = None
    referencia_percentiles: str | None = None
    observaciones: str | None = None


@dataclass(frozen=True, slots=True)
class TipoVacuna:
    id_vacuna: str
    nombre: str
    enfermedades_que_previene: str | None = None
    edad_recomendada_meses: int | None = None
    dosis_sugerida: str | None = None


@dataclass(frozen=True, slots=True)
class DescripcionVacuna:
    """Lo que el administrador puede corregir de una vacuna del catalogo (el nombre no:
    los esquemas de los pacientes ya la muestran con ese nombre).

    edad_recomendada_meses es la edad de la primera dosis; sin ella, "generar esquema
    recomendado" no la programa.
    """

    enfermedades_que_previene: str | None = None
    edad_recomendada_meses: int | None = None
    dosis_sugerida: str | None = None

    def validar(self) -> None:
        edad = self.edad_recomendada_meses
        if edad is not None and not 0 <= edad <= EDAD_MAXIMA_MESES:
            raise DatosInvalidos(
                f"La edad recomendada va de 0 a {EDAD_MAXIMA_MESES} meses (18 anos)."
            )


def nombre_de_vacuna(texto: str) -> str:
    limpio = " ".join(texto.split())
    if not limpio:
        raise DatosInvalidos("Escribe el nombre de la vacuna.")
    return limpio


class EstadoDosis(StrEnum):
    PENDIENTE = "pendiente"
    APLICADA = "aplicada"
    CANCELADA = "cancelada"


@dataclass(frozen=True, slots=True)
class DosisVacuna:
    id_dosis: str
    id_paciente: str
    id_vacuna: str
    nombre_vacuna: str
    estado: EstadoDosis
    numero_dosis: int | None = None
    fecha_programada: date | None = None
    fecha_aplicacion: datetime | None = None
    id_aplicador: str | None = None
    observaciones_reaccion: str | None = None


def meses_cumplidos(nacimiento: date, hoy: date) -> int:
    meses = (hoy.year - nacimiento.year) * 12 + hoy.month - nacimiento.month
    return max(meses - (1 if hoy.day < nacimiento.day else 0), 0)


def sumar_meses(fecha: date, meses: int) -> date:
    indice = fecha.year * 12 + fecha.month - 1 + meses
    anio, mes = divmod(indice, 12)
    return date(anio, mes + 1, min(fecha.day, monthrange(anio, mes + 1)[1]))
