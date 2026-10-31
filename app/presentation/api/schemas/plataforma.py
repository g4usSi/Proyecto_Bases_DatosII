from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.institucion import Institucion


class IndicadoresResponse(BaseModel):
    """null en un campo = no aplica a esa entidad."""

    model_config = ConfigDict(from_attributes=True)

    pacientes_registrados: int
    citas_hoy: int | None = None
    citas_semana: int | None = None
    camas_ocupadas: int | None = None
    camas_total: int | None = None
    emergencias_activas: int | None = None
    cobros_por_cobrar: int | None = Field(
        default=None, description="Hospital: cobros abiertos o cerrados. Pediatrico: facturas."
    )
    saldo_por_cobrar: Decimal | None = None
    ordenes_abiertas: int | None = None


class ResumenEntidadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    institucion: Institucion
    administrador: str | None = Field(description="Nombre del administrador activo")
    personal_activo: int
    personal_sin_acceso: int = Field(description="Cuentas bloqueadas o deshabilitadas")
    indicadores: IndicadoresResponse | None = Field(
        description="null si el motor de la entidad no respondio"
    )


class ResumenPlataformaResponse(BaseModel):
    entidades: list[ResumenEntidadResponse]

    @classmethod
    def de(cls, resumen) -> "ResumenPlataformaResponse":
        return cls(entidades=[ResumenEntidadResponse.model_validate(e) for e in resumen.entidades])
