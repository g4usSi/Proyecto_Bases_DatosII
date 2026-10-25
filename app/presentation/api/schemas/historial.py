"""Contrato HTTP comun de consultas. La interfaz no cambia segun el motor."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.presentation.api.schemas.paciente import PacienteResponse

Corto = Field(min_length=1, max_length=200)


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class DiagnosticoSchema(Entrada):
    descripcion: str = Field(min_length=1, max_length=500)
    codigo: str | None = Field(default=None, max_length=20)
    sistema_codigo: str | None = Field(default=None, max_length=20)


class TratamientoSchema(Entrada):
    descripcion: str = Field(min_length=1, max_length=1000)


class RecetaSchema(Entrada):
    medicamento: str = Corto
    dosis: str = Corto
    frecuencia: str = Corto
    via_administracion: str | None = Field(default=None, max_length=100)
    duracion_dias: int | None = Field(default=None, ge=1, le=3650)
    instrucciones: str | None = Field(default=None, max_length=1000)


class ConsultaCrear(Entrada):
    motivo: str = Field(min_length=1, max_length=500)
    notas: str | None = Field(default=None, max_length=5000)
    # Los mismos limites que el validador de MongoDB (maxItems: 100).
    diagnosticos: list[DiagnosticoSchema] = Field(default_factory=list, max_length=100)
    tratamientos: list[TratamientoSchema] = Field(default_factory=list, max_length=100)
    recetas: list[RecetaSchema] = Field(default_factory=list, max_length=100)


class AdendaCrear(Entrada):
    """Lo que se agrega a una consulta ya guardada. Al menos un elemento."""

    nota: str | None = Field(default=None, max_length=2000)
    diagnosticos: list[DiagnosticoSchema] = Field(default_factory=list, max_length=100)
    tratamientos: list[TratamientoSchema] = Field(default_factory=list, max_length=100)
    recetas: list[RecetaSchema] = Field(default_factory=list, max_length=100)


class ConsultaResponse(Entrada):
    id_consulta: str
    id_paciente: str
    id_profesional: str
    fecha_hora: datetime
    motivo: str
    notas: str | None = None
    diagnosticos: list[DiagnosticoSchema]
    tratamientos: list[TratamientoSchema]
    recetas: list[RecetaSchema]


class HistorialResponse(BaseModel):
    paciente: PacienteResponse
    consultas: list[ConsultaResponse]
    siguiente_antes_de: datetime | None = Field(
        default=None, description="Enviar como ?antes_de= para pedir la pagina siguiente."
    )
