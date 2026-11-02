from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.domain.administracion import EstadoCuenta
from app.domain.institucion import Institucion

Nombre = Field(min_length=1, max_length=120)


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfesionalCrear(Entrada):
    establecimiento: Institucion | None = Field(
        default=None, description="Solo para el superusuario; obligatorio en ese caso."
    )
    correo: str = Field(min_length=3, max_length=254)
    nombres: str = Nombre
    apellidos: str = Nombre
    rol: str = Field(min_length=1, max_length=40)
    id_departamento: int | None = Field(
        default=None, ge=1, description="Area del profesional (solo Hospital General)."
    )
    permisos: list[str] | None = Field(
        default=None,
        max_length=30,
        description="Si se omite, los permisos base del rol. pacientes:leer siempre se incluye.",
    )
    contrasena_inicial: SecretStr | None = Field(
        default=None,
        min_length=12,
        max_length=128,
        description="Si se omite, se genera una y se devuelve una sola vez.",
    )


class ProfesionalCambios(Entrada):
    """Solo los campos enviados cambian. `id_departamento: null` quita el area."""

    nombres: str | None = Field(default=None, min_length=1, max_length=120)
    apellidos: str | None = Field(default=None, min_length=1, max_length=120)
    id_departamento: int | None = Field(default=None, ge=1)
    permisos: list[str] | None = Field(
        default=None, max_length=30, description="Reemplaza la lista completa de permisos."
    )
    estado: Literal["activa", "bloqueada", "inactiva"] | None = None


class ProfesionalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_profesional: str
    correo: str
    nombres: str
    apellidos: str
    rol: str
    institucion: Institucion
    estado: EstadoCuenta
    permisos: list[str]
    id_departamento: int | None = None
    departamento: str | None = None
    debe_cambiar_contrasena: bool = False
    creado_en: datetime | None = None
    actualizado_en: datetime | None = None

    @field_validator("permisos", mode="before")
    @classmethod
    def ordenar(cls, valor: object) -> object:
        return sorted(valor) if isinstance(valor, (set, frozenset, list, tuple)) else valor


class ProfesionalCreadoResponse(BaseModel):
    profesional: ProfesionalResponse
    vinculado: bool = Field(
        description="False si el perfil local en el motor de la institucion no se pudo crear; "
        "repetir con scripts/sincronizar_profesionales.py."
    )
    contrasena_temporal: str | None = Field(
        default=None, description="Solo cuando se genero: se muestra una vez y no se guarda."
    )


class ProfesionalCambiadoResponse(BaseModel):
    profesional: ProfesionalResponse
    vinculado: bool | None = None


class ContrasenaRestablecidaResponse(BaseModel):
    contrasena_temporal: str
    mensaje: str = (
        "Entregala a la persona por un medio seguro. No se volvera a mostrar; al iniciar sesion "
        "debera elegir una propia. Sus sesiones abiertas se cerraron."
    )


class ProfesionalAgendaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_profesional: str
    nombres: str
    apellidos: str
    rol: str
    id_departamento: int | None = None


class DepartamentoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_departamento: int
    nombre: str
    habitaciones: int = 0
    camas: int = 0
    camas_disponibles: int = 0


class CambiarContrasenaRequest(Entrada):
    contrasena_actual: SecretStr = Field(min_length=1, max_length=1024)
    contrasena_nueva: SecretStr = Field(min_length=12, max_length=128)


class EventoProfesionalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_evento: int
    ocurrido_en: datetime
    institucion: Institucion | None
    actor: str
    rol_actor: str
    id_profesional: str
    cuenta: str
    accion: str
    detalle: dict


class ResumenPersonalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    por_estado: dict[str, int]
    bloqueadas_por_intentos: int
    pendientes_cambio_contrasena: int
    activos_por_rol: dict[str, int]
    activos_por_departamento: dict[str, int] | None
    ultimos_movimientos: list[EventoProfesionalResponse]
