from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.paciente import Alergia, Contacto, MotivoBaja

Texto = Field(min_length=1, max_length=120)


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, from_attributes=True)


class ContactoSchema(Entrada):
    telefono: str | None = Field(default=None, max_length=30)
    correo: str | None = Field(default=None, max_length=254)
    direccion: str | None = Field(default=None, max_length=300)

    def a_dominio(self) -> Contacto:
        return Contacto(self.telefono, self.correo, self.direccion)


class AlergiaSchema(Entrada):
    sustancia: str = Texto
    reaccion: str | None = Field(default=None, max_length=300)
    severidad: str | None = Field(default=None, max_length=50)

    def a_dominio(self) -> Alergia:
        return Alergia(self.sustancia, self.reaccion, self.severidad)


class PacienteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_paciente: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date | None = None
    archivado: bool = False
    contacto: ContactoSchema | None = None
    grupo_sanguineo: str | None = None
    alergias: list[AlergiaSchema] | None = Field(
        default=None,
        description=(
            "null: alergias no evaluadas, el motor no las guarda o no tienes permiso "
            "clinico (historiales:leer). []: evaluadas, sin alergias conocidas."
        ),
    )


class PacienteResumen(BaseModel):
    """Fila de una busqueda: sin contacto ni alergias."""

    model_config = ConfigDict(from_attributes=True)

    id_paciente: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date | None = None
    archivado: bool = False


class PacienteCrear(Entrada):
    nombres: str = Texto
    apellidos: str = Texto
    fecha_nacimiento: date | None = None
    contacto: ContactoSchema | None = None
    alergias: list[AlergiaSchema] | None = Field(
        default=None,
        max_length=50,
        description="Omitir si no se han evaluado. Enviar [] si se evaluaron y no tiene.",
    )

    @field_validator("fecha_nacimiento")
    @classmethod
    def no_futura(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("La fecha de nacimiento no puede ser futura.")
        return value


class PacienteActualizar(Entrada):
    """Correccion de datos demograficos. Los campos omitidos no cambian."""

    nombres: str | None = Field(default=None, min_length=1, max_length=120)
    apellidos: str | None = Field(default=None, min_length=1, max_length=120)
    fecha_nacimiento: date | None = None
    contacto: ContactoSchema | None = Field(
        default=None, description="Si se envia, REEMPLAZA el contacto completo."
    )

    @field_validator("fecha_nacimiento")
    @classmethod
    def no_futura(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("La fecha de nacimiento no puede ser futura.")
        return value


class AlergiasAgregar(Entrada):
    alergias: list[AlergiaSchema] = Field(min_length=1, max_length=50)


class ArchivoCrear(Entrada):
    motivo: MotivoBaja
    detalle: str | None = Field(default=None, max_length=500)


class ArchivoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    motivo: MotivoBaja
    detalle: str | None
    fecha: datetime
    id_profesional: str
