from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.hospital import EstadoCama, TipoIngreso, TipoOrdenMedica
from app.presentation.api.schemas.historial import DiagnosticoSchema, Entrada, RecetaSchema


class OcupanteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_ingreso: str
    id_paciente: str
    nombre_paciente: str
    tipo: TipoIngreso
    desde: datetime


class CamaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_cama: int
    codigo: str
    id_habitacion: int
    habitacion: str
    id_departamento: int
    departamento: str
    estado: EstadoCama
    ocupante: OcupanteResponse | None = None


class EstadoCamaCambio(Entrada):
    estado: EstadoCama = Field(description="disponible, limpieza o mantenimiento")


class IngresoCrear(Entrada):
    id_cama: int = Field(ge=1)
    tipo: TipoIngreso
    motivo: str = Field(min_length=1, max_length=500)
    diagnosticos: list[DiagnosticoSchema] = Field(default_factory=list, max_length=50)


class OrdenMedicaCrear(Entrada):
    tipo: TipoOrdenMedica
    descripcion: str | None = Field(default=None, max_length=500)
    recetas: list[RecetaSchema] = Field(
        default_factory=list, max_length=50, description="Solo para tipo medicamento"
    )


class AltaCrear(Entrada):
    motivo: str = Field(min_length=1, max_length=300)


class OrdenMedicaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_orden: str
    tipo: TipoOrdenMedica
    fecha_hora: datetime
    id_profesional: str
    descripcion: str | None = None
    recetas: list[RecetaSchema]


class IngresoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_ingreso: str
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
    abierto: bool
    diagnosticos: list[DiagnosticoSchema]
    ordenes: list[OrdenMedicaResponse]


class ResumenHospitalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    camas_por_estado: dict[str, int]
    camas_total: int
    ocupacion: float = Field(description="Porcentaje de camas ocupadas (0-100)")
    ingresos_abiertos: int
    emergencias_abiertas: int
    ingresos_hoy: int
    altas_hoy: int
    citas_hoy_por_estado: dict[str, int]
