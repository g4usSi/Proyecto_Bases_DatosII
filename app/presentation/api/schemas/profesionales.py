from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.domain.administracion import AccionBitacora, EstadoCuenta
from app.domain.institucion import Institucion

Nombre = Field(min_length=1, max_length=120)


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProfesionalCrear(Entrada):
    correo: str = Field(min_length=3, max_length=254)
    nombres: str = Nombre
    apellidos: str = Nombre
    rol: str = Field(min_length=1, max_length=40)
    establecimiento: Institucion | None = Field(
        default=None,
        description="Solo la administracion general (obligatorio para ella). El administrador "
        "de una entidad no lo envia: la cuenta se crea en su institucion (enviarlo es 422).",
    )
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
    estado: EstadoCuenta | None = Field(
        default=None,
        description="activa, bloqueada o inactiva. Eliminar solo se hace con DELETE (422).",
    )


class ProfesionalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_profesional: str
    correo: str
    nombres: str
    apellidos: str
    rol: str
    institucion: Institucion | None
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
    vinculado: bool | None = Field(
        description="False si el perfil local en el motor de la institucion no se pudo crear; "
        "repetir con scripts/sincronizar_profesionales.py. null para una cuenta de "
        "administracion (no tiene perfil local)."
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


class CuentaAtencionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_profesional: str
    nombres: str
    apellidos: str
    rol: str
    estado: EstadoCuenta
    motivo: str = Field(description="bloqueo_por_intentos o debe_cambiar_contrasena")


class AreaPersonalResponse(BaseModel):
    id_departamento: int
    nombre: str
    activos: int


class EntradaBitacoraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_evento: int
    ocurrido_en: datetime
    accion: AccionBitacora
    id_actor: str
    actor_nombre: str | None
    actor_rol: str | None = Field(description="superusuario, administrador u otro rol")
    id_profesional: str
    profesional_nombre: str
    institucion: Institucion | None = Field(
        description="Entidad de la cuenta afectada (null: el superusuario sobre su cuenta)."
    )
    detalle: dict = Field(description="Que cambio. Nunca contrasenas ni hashes.")


class ResumenPersonalResponse(BaseModel):
    institucion: Institucion
    administrador: str | None = Field(description="Nombre del administrador activo")
    por_estado: dict[str, int] = Field(description="Personal (sin administracion) por estado")
    bloqueadas_por_intentos: int
    bloqueadas_por_administracion: int
    deben_cambiar_contrasena: int
    activos_por_rol: dict[str, int]
    activos_por_area: list[AreaPersonalResponse] | None = Field(description="Solo Hospital General")
    requieren_atencion: list[CuentaAtencionResponse]
    ultimos_movimientos: list[EntradaBitacoraResponse]

    @classmethod
    def de(cls, resumen) -> "ResumenPersonalResponse":
        return cls(
            institucion=resumen.institucion,
            administrador=resumen.administrador,
            por_estado=resumen.por_estado,
            bloqueadas_por_intentos=resumen.bloqueadas_por_intentos,
            bloqueadas_por_administracion=resumen.bloqueadas_por_administracion,
            deben_cambiar_contrasena=resumen.deben_cambiar_contrasena,
            activos_por_rol=resumen.activos_por_rol,
            activos_por_area=(
                None
                if resumen.activos_por_area is None
                else [
                    AreaPersonalResponse(id_departamento=i, nombre=n, activos=t)
                    for i, n, t in resumen.activos_por_area
                ]
            ),
            requieren_atencion=[
                CuentaAtencionResponse.model_validate(c) for c in resumen.requieren_atencion
            ],
            ultimos_movimientos=[
                EntradaBitacoraResponse.model_validate(e) for e in resumen.ultimos_movimientos
            ],
        )
