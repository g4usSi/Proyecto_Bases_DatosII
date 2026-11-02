"""Administracion institucional y de plataforma (cuentas de la identidad central).

Reglas (decisiones del equipo, brecha-api-frontend):
- Un administrador por institucion, con un unico permiso (profesionales:administrar) y sin
  permisos clinicos. Solo gestiona al personal de SU institucion: la institucion sale del
  token, nunca del formulario.
- Los permisos se dan por profesional, no por rol. El rol fija solo la base
  (pacientes:leer, o los de secretaria/laboratorista/odontologo si no se indican otros).
- La secretaria existe solo en la Clinica Odontologica y nunca tiene permisos clinicos.
- El superusuario sin institucion crea administradores por la API y es el unico que
  elimina cuentas. Se aprovisiona y recupera con scripts locales.
"""

import secrets
import string
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain import permisos as p
from app.domain.errores import AccesoDenegado, DatosInvalidos
from app.domain.institucion import Institucion

ROL_ADMINISTRADOR = "administrador"
ROL_SUPERUSUARIO = "superusuario"

# Roles que un administrador puede dar de alta en su institucion.
ROLES_POR_INSTITUCION: dict[Institucion, frozenset[str]] = {
    Institucion.HOSPITAL_GENERAL: frozenset({"medico", "enfermeria"}),
    Institucion.CENTRO_PEDIATRICO: frozenset({"medico", "enfermeria"}),
    Institucion.LABORATORIO_CLINICO: frozenset({"laboratorista", "medico"}),
    Institucion.CLINICA_ODONTOLOGICA: frozenset({"odontologo", "secretaria"}),
}

_COMUNES = frozenset(
    {
        p.PACIENTES_LEER,
        p.PACIENTES_REGISTRAR,
        p.HISTORIALES_LEER,
        p.CONSULTAS_REGISTRAR,
        p.HISTORIALES_ARCHIVAR,
        p.CITAS_LEER,
        p.CITAS_GESTIONAR,
    }
)

# Permisos que tienen sentido en cada institucion (otro -> 422).
PERMISOS_ASIGNABLES: dict[Institucion, frozenset[str]] = {
    Institucion.HOSPITAL_GENERAL: _COMUNES | {p.CAMAS_GESTIONAR, p.PAGOS_VER, p.PAGOS_REGISTRAR},
    Institucion.CENTRO_PEDIATRICO: _COMUNES | {p.PAGOS_VER, p.PAGOS_REGISTRAR},
    Institucion.LABORATORIO_CLINICO: _COMUNES | {p.LABORATORIO_RESULTADOS, p.LABORATORIO_VALIDAR},
    Institucion.CLINICA_ODONTOLOGICA: _COMUNES,
}

LARGO_MINIMO_CONTRASENA = 12
LARGO_MAXIMO_CONTRASENA = 128


class EstadoCuenta(StrEnum):
    ACTIVA = "activa"
    BLOQUEADA = "bloqueada"  # no puede iniciar sesion (por administracion o por intentos)
    INACTIVA = "inactiva"  # ya no forma parte del personal
    ELIMINADA = "eliminada"  # irreversible; solo por DELETE


@dataclass(frozen=True, slots=True)
class FichaProfesional:
    """Lo que ve el administrador. Nunca incluye la contrasena ni su hash."""

    id_profesional: str
    correo: str
    nombres: str
    apellidos: str
    rol: str
    institucion: Institucion
    estado: EstadoCuenta
    permisos: frozenset[str]
    id_departamento: int | None = None
    departamento: str | None = None
    debe_cambiar_contrasena: bool = False
    creado_en: datetime | None = None
    actualizado_en: datetime | None = None


@dataclass(frozen=True, slots=True)
class NuevoProfesional:
    correo: str
    nombres: str
    apellidos: str
    rol: str
    permisos: frozenset[str] | None = None  # None = permisos base del rol
    id_departamento: int | None = None


@dataclass(frozen=True, slots=True)
class CambiosProfesional:
    """None = no cambia. Para quitar el area se usa quitar_departamento."""

    nombres: str | None = None
    apellidos: str | None = None
    permisos: frozenset[str] | None = None
    estado: EstadoCuenta | None = None
    id_departamento: int | None = None
    quitar_departamento: bool = False

    @property
    def vacio(self) -> bool:
        return (
            self.nombres is None
            and self.apellidos is None
            and self.permisos is None
            and self.estado is None
            and self.id_departamento is None
            and not self.quitar_departamento
        )


@dataclass(frozen=True, slots=True)
class ProfesionalAgenda:
    """Lo minimo para elegir con quien agendar (sin correo ni permisos)."""

    id_profesional: str
    nombres: str
    apellidos: str
    rol: str
    id_departamento: int | None = None


@dataclass(frozen=True, slots=True)
class EventoProfesional:
    id_evento: int
    ocurrido_en: datetime
    institucion: Institucion | None
    actor: str
    rol_actor: str
    id_profesional: str
    cuenta: str
    accion: str
    detalle: dict


@dataclass(frozen=True, slots=True)
class ResumenPersonal:
    por_estado: dict[str, int]
    bloqueadas_por_intentos: int
    pendientes_cambio_contrasena: int
    activos_por_rol: dict[str, int]
    activos_por_departamento: dict[str, int] | None
    ultimos_movimientos: list[EventoProfesional]
    administrador_activo: str | None = None


def validar_rol(institucion: Institucion, rol: str, *, actor_es_superusuario: bool = False) -> None:
    if rol == ROL_ADMINISTRADOR:
        if not actor_es_superusuario:
            raise AccesoDenegado("Solo el superusuario puede crear administradores.")
        return
    if rol not in ROLES_POR_INSTITUCION[institucion]:
        validos = ", ".join(sorted(ROLES_POR_INSTITUCION[institucion]))
        raise DatosInvalidos(f"Rol no valido para tu institucion. Roles permitidos: {validos}.")


def permisos_finales(
    institucion: Institucion, rol: str, pedidos: frozenset[str] | None
) -> frozenset[str]:
    """Permisos que quedaran guardados. Lanza DatosInvalidos si no son compatibles."""
    elegidos = (
        frozenset(pedidos)
        if pedidos is not None
        else p.PERMISOS_POR_ROL.get(rol, p.PERMISOS_POR_DEFECTO)
    )
    if rol == ROL_ADMINISTRADOR:
        if elegidos != {p.PROFESIONALES_ADMINISTRAR}:
            raise DatosInvalidos("El administrador tiene solo profesionales:administrar.")
        return frozenset(elegidos)
    elegidos = elegidos | {p.PACIENTES_LEER}  # base de todo el personal
    if p.PROFESIONALES_ADMINISTRAR in elegidos:
        raise DatosInvalidos(
            "profesionales:administrar es exclusivo de la cuenta de administracion."
        )
    fuera = elegidos - PERMISOS_ASIGNABLES[institucion]
    if fuera:
        raise DatosInvalidos(
            "Permisos que no aplican a tu institucion: " + ", ".join(sorted(fuera)) + "."
        )
    if rol == "secretaria":
        vedados = elegidos & p.PERMISOS_VEDADOS_SECRETARIA
        if vedados:
            raise DatosInvalidos(
                "Una secretaria no puede tener permisos clinicos ni archivar historiales: "
                + ", ".join(sorted(vedados))
                + "."
            )
    return elegidos


def validar_departamento(institucion: Institucion, id_departamento: int | None) -> None:
    if id_departamento is not None and institucion != Institucion.HOSPITAL_GENERAL:
        raise DatosInvalidos("El area (departamento) solo aplica al Hospital General.")


def normalizar_correo(correo: str) -> str:
    correo = correo.strip().lower()
    local, arroba, dominio = correo.partition("@")
    if not arroba or not local or "." not in dominio or any(c.isspace() for c in correo):
        raise DatosInvalidos("Correo invalido.")
    return correo


def validar_contrasena(contrasena: str, correo: str | None = None) -> None:
    """Politica minima: largo, mezcla de letras y otros caracteres, sin el correo."""
    if not LARGO_MINIMO_CONTRASENA <= len(contrasena) <= LARGO_MAXIMO_CONTRASENA:
        raise DatosInvalidos(
            f"La contrasena debe tener entre {LARGO_MINIMO_CONTRASENA} y "
            f"{LARGO_MAXIMO_CONTRASENA} caracteres."
        )
    if contrasena.strip() != contrasena or not contrasena.strip():
        raise DatosInvalidos("La contrasena no puede empezar ni terminar con espacios.")
    if not any(c.isalpha() for c in contrasena) or all(c.isalpha() for c in contrasena):
        raise DatosInvalidos("La contrasena debe combinar letras con numeros o simbolos.")
    if len(set(contrasena)) < 5:
        raise DatosInvalidos("La contrasena es demasiado repetitiva.")
    if correo:
        usuario = correo.split("@", 1)[0].lower()
        if len(usuario) >= 4 and usuario in contrasena.lower():
            raise DatosInvalidos("La contrasena no puede contener tu correo.")


def generar_contrasena(largo: int = 16) -> str:
    """Contrasena aleatoria que cumple la politica (se muestra una sola vez)."""
    alfabeto = string.ascii_letters + string.digits + "-_.!@#"
    while True:
        candidata = "".join(secrets.choice(alfabeto) for _ in range(largo))
        if (
            any(c.islower() for c in candidata)
            and any(c.isupper() for c in candidata)
            and any(c.isdigit() for c in candidata)
            and candidata.strip() == candidata
        ):
            return candidata
