from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.odontograma import EstadoDental, Superficie


class PiezaActualizar(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    estado: EstadoDental
    superficies: list[Superficie] = Field(default_factory=list, max_length=7)
    nota: str | None = Field(default=None, max_length=500)


class PiezaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    pieza: str
    estado: EstadoDental
    superficies: list[Superficie]
    nota: str | None
    actualizado_por: str
    actualizado_en: datetime


class OdontogramaResponse(BaseModel):
    id_paciente: str
    piezas: list[PiezaResponse]
