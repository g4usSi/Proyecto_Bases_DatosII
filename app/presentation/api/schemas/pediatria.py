from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.pediatria import EDAD_MAXIMA_MESES, EstadoDosis


class ControlCrear(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    peso_kg: float | None = Field(default=None, gt=0, le=300)
    talla_cm: float | None = Field(default=None, gt=0, le=250)
    perimetro_cefalico: float | None = Field(default=None, gt=0, le=100)
    percentil_peso: float | None = Field(default=None, ge=0, le=100)
    percentil_talla: float | None = Field(default=None, ge=0, le=100)
    referencia_percentiles: str | None = Field(default=None, min_length=1, max_length=150)
    observaciones: str | None = Field(default=None, min_length=1, max_length=2000)


class ControlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_control: str
    id_paciente: str
    fecha_registro: datetime
    edad_meses: int | None
    peso_kg: float | None
    talla_cm: float | None
    perimetro_cefalico: float | None
    percentil_peso: float | None
    percentil_talla: float | None
    referencia_percentiles: str | None
    observaciones: str | None


class TipoVacunaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_vacuna: str
    nombre: str
    enfermedades_que_previene: str | None
    edad_recomendada_meses: int | None
    dosis_sugerida: str | None


class DescripcionVacunaSchema(BaseModel):
    """Se envia completa: un campo ausente o null queda vacio."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enfermedades_que_previene: str | None = Field(default=None, max_length=1000)
    edad_recomendada_meses: int | None = Field(
        default=None,
        ge=0,
        le=EDAD_MAXIMA_MESES,
        description="Edad de la primera dosis; sin ella no entra al esquema recomendado",
    )
    dosis_sugerida: str | None = Field(default=None, max_length=100)


class TipoVacunaCrear(DescripcionVacunaSchema):
    nombre: str = Field(min_length=1, max_length=150)


class DosisProgramar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_vacuna: str = Field(min_length=1, max_length=20, pattern=r"^\d+$")
    numero_dosis: int | None = Field(default=None, ge=1, le=20)
    fecha_programada: date | None = None


class DosisAplicar(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    observaciones_reaccion: str | None = Field(default=None, min_length=1, max_length=1000)


class DosisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_dosis: str
    id_paciente: str
    id_vacuna: str
    nombre_vacuna: str
    estado: EstadoDosis
    numero_dosis: int | None
    fecha_programada: date | None
    fecha_aplicacion: datetime | None
    id_aplicador: str | None
    observaciones_reaccion: str | None
