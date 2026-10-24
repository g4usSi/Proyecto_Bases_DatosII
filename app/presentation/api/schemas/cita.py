from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.domain.cita import EstadoCita


class CitaCrear(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id_paciente: str = Field(min_length=1, max_length=128)
    id_profesional: str = Field(min_length=1, max_length=64, description="UUID del profesional")
    inicio: AwareDatetime = Field(description="Con zona, p. ej. 2026-11-03T09:00:00-06:00")
    duracion_minutos: int = Field(ge=5, le=480)
    motivo: str = Field(min_length=1, max_length=300)


class CambioEstadoCita(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    estado: EstadoCita = Field(description="atendida, cancelada o no_asistio")
    motivo: str | None = Field(default=None, max_length=300)


class CitaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_cita: str
    id_paciente: str
    nombre_paciente: str
    id_profesional: str
    inicio: datetime
    fin: datetime
    motivo: str
    estado: EstadoCita
    creada_por: str
    motivo_cambio: str | None = None
