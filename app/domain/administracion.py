"""Administracion de cuentas de la identidad central, en dos niveles.

Reglas (decisiones del equipo, docs/administracion_general.md):
- Superusuario de plataforma: UNA cuenta, sin institucion ni permisos clinicos. Crea
  cuentas en cualquier entidad (incluido su administrador), deshabilita, rehabilita y es el
  unico que elimina (baja definitiva logica). Nunca se gestiona a si mismo por la API.
- Administrador de cada entidad: uno ACTIVO por entidad, con un unico permiso
  (profesionales:administrar). Solo gestiona al personal de SU institucion, que sale del
  token y nunca del formulario. No crea administradores ni elimina.
- Los permisos se dan por profesional, no por rol. El rol fija solo la base
  (pacientes:leer, o los de la secretaria/laboratorista si no se indican otros).
- La secretaria existe solo en la Clinica Odontologica y nunca tiene permisos clinicos.
- El superusuario se crea con scripts/crear_profesional.py, nunca por la API.
"""

import secrets
import string
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain import permisos as p
from app.domain.errores import AccesoDenegado, DatosInvalidos
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion

ROL_ADMINISTRADOR = "administrador"
ROL_SUPERUSUARIO = "superusuario"
ROLES_DE_ADMINISTRACION = frozenset({ROL_ADMINISTRADOR, ROL_SUPERUSUARIO})

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
    INACTIVA = "inactiva"  # deshabilitada: se puede rehabilitar
    ELIMINADA = "eliminada"  # baja definitiva (solo DELETE del superusuario); no se asigna


# Estados que se pueden pedir por PATCH. Eliminar solo se hace con DELETE.
ESTADOS_ASIGNABLES = frozenset({EstadoCuenta.ACTIVA, EstadoCuenta.BLOQUEADA, EstadoCuenta.INACTIVA})


@dataclass(frozen=True, slots=True)
class FichaProfesional:
    """Lo que ve el administrador. Nunca incluye la contrasena ni su hash."""

    id_profesional: str
    correo: str
    nombres: str
    apellidos: str
    rol: str
    institucion: Institucion | None
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


class AccionBitacora(StrEnum):
    ALTA = "alta"
    CAMBIO = "cambio"
    RESTABLECER_CONTRASENA = "restablecer_contrasena"
    CAMBIAR_CONTRASENA = "cambiar_contrasena"
    ELIMINAR = "eliminar"


@dataclass(frozen=True, slots=True)
class EntradaBitacora:
    """Un movimiento de administracion. La tabla nunca guarda contrasenas ni hashes."""

    id_evento: int
    ocurrido_en: datetime
    accion: AccionBitacora
    id_actor: str
    actor_nombre: str | None  # None si el actor ya no existe en la identidad central
    actor_rol: str | None
    id_profesional: str
    profesional_nombre: str
    institucion: Institucion | None  # None: el superusuario sobre su propia cuenta
    detalle: dict


@dataclass(frozen=True, slots=True)
class FiltroBitacora:
    acciones: frozenset[AccionBitacora] | None = None
    desde: datetime | None = None
    hasta: datetime | None = None
    antes_de: int | None = None  # cursor: id_evento de la ultima fila recibida
    limite: int = 50


@dataclass(frozen=True, slots=True)
class CuentaAtencion:
    """Cuenta que el administrador deberia revisar (solo datos de la cuenta)."""

    id_profesional: str
    nombres: str
    apellidos: str
    rol: str
    estado: EstadoCuenta
    motivo: str  # bloqueo_por_intentos | bloqueo_administrativo | debe_cambiar_contrasena


@dataclass(frozen=True, slots=True)
class ResumenPersonal:
    """Resumen del personal de UNA entidad. Sale de identidad.profesional y de la bitacora;
    nunca toca un motor clinico."""

    institucion: Institucion
    administrador: str | None  # nombre del administrador activo, o None
    por_estado: dict[str, int]
    bloqueadas_por_intentos: int
    bloqueadas_por_administracion: int
    deben_cambiar_contrasena: int
    activos_por_rol: dict[str, int]
    activos_por_area: tuple[tuple[int, str, int], ...] | None  # solo Hospital General
    requieren_atencion: tuple[CuentaAtencion, ...]
    ultimos_movimientos: tuple[EntradaBitacora, ...]


@dataclass(frozen=True, slots=True)
class Alcance:
    """Que cuentas puede ver y gestionar quien administra.

    institucion None = las cuatro entidades (solo el superusuario). El superusuario nunca
    aparece en un alcance y las cuentas eliminadas no salen en los listados.
    """

    institucion: Institucion | None
    incluir_administradores: bool = False


def es_superusuario(actor: UsuarioAutenticado) -> bool:
    return actor.es_plataforma and p.PLATAFORMA_ADMINISTRAR in actor.permisos


def alcance_de(actor: UsuarioAutenticado, pedida: Institucion | None = None) -> Alcance:
    """Superusuario: todas las entidades o la pedida. Administrador: solo la suya.

    Un administrador que pide otra entidad recibe 403 (no puede ver fuera de la suya).
    """
    if es_superusuario(actor):
        return Alcance(pedida, incluir_administradores=True)
    if actor.institucion is None or p.PROFESIONALES_ADMINISTRAR not in actor.permisos:
        raise AccesoDenegado("No tienes permiso para realizar esta operacion.")
    if pedida is not None and pedida != actor.institucion:
        raise AccesoDenegado("Solo puedes administrar el personal de tu institucion.")
    return Alcance(actor.institucion, incluir_administradores=False)


def puede_gestionar(actor: UsuarioAutenticado, objetivo: "FichaProfesional") -> bool:
    """El superusuario gestiona cualquier cuenta menos la suya; el administrador, solo las de
    su entidad que no sean de administracion."""
    if objetivo.rol == ROL_SUPERUSUARIO or objetivo.id_profesional == actor.id_usuario:
        return False
    if es_superusuario(actor):
        return True
    return (
        actor.institucion is not None
        and objetivo.institucion == actor.institucion
        and objetivo.rol not in ROLES_DE_ADMINISTRACION
    )


def validar_rol(institucion: Institucion, rol: str, *, actor_es_superusuario: bool = False) -> None:
    if rol == ROL_SUPERUSUARIO:
        raise DatosInvalidos("El superusuario se crea con scripts/crear_profesional.py.")
    if rol == ROL_ADMINISTRADOR:
        if not actor_es_superusuario:
            raise AccesoDenegado(
                "Solo la administracion general crea la cuenta de administracion de una entidad."
            )
        return
    if rol not in ROLES_POR_INSTITUCION[institucion]:
        validos = ", ".join(sorted(ROLES_POR_INSTITUCION[institucion]))
        raise DatosInvalidos(f"Rol no valido para esa institucion. Roles permitidos: {validos}.")


def permisos_finales(
    institucion: Institucion, rol: str, pedidos: frozenset[str] | None
) -> frozenset[str]:
    """Permisos que quedaran guardados. Lanza DatosInvalidos si no son compatibles."""
    if p.PLATAFORMA_ADMINISTRAR in (pedidos or frozenset()):
        raise DatosInvalidos("plataforma:administrar es exclusivo del superusuario.")
    if rol == ROL_ADMINISTRADOR:
        # La cuenta de administracion tiene un unico permiso y nunca uno clinico.
        unico = frozenset({p.PROFESIONALES_ADMINISTRAR})
        if pedidos is not None and frozenset(pedidos) - unico:
            raise DatosInvalidos(
                "La cuenta de administracion solo tiene profesionales:administrar."
            )
        return unico
    elegidos = (
        frozenset(pedidos)
        if pedidos is not None
        else p.PERMISOS_POR_ROL.get(rol, p.PERMISOS_POR_DEFECTO)
    )
    elegidos = elegidos | {p.PACIENTES_LEER}  # base de todo el personal
    if p.PROFESIONALES_ADMINISTRAR in elegidos:
        raise DatosInvalidos(
            "profesionales:administrar es exclusivo de la cuenta de administracion."
        )
    fuera = elegidos - PERMISOS_ASIGNABLES[institucion]
    if fuera:
        raise DatosInvalidos(
            "Permisos que no aplican a esa institucion: " + ", ".join(sorted(fuera)) + "."
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
