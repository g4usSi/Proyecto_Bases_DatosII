from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.presentation.api.schemas.historial import Entrada


class TutorNuevoSchema(Entrada):
    nombres: str = Field(min_length=1, max_length=100)
    apellidos: str = Field(min_length=1, max_length=100)
    documento: str | None = Field(
        default=None, min_length=1, max_length=30, description="DPI o pasaporte"
    )
    telefono: str | None = Field(default=None, max_length=30)
    correo: str | None = Field(default=None, max_length=254)
    direccion: str | None = Field(default=None, max_length=300)
    religion: str | None = Field(default=None, max_length=100, description="Opcional")


class TutorVincular(Entrada):
    """Un tutor existente (id_tutor, p. ej. de un hermano) o uno nuevo (tutor)."""

    id_tutor: str | None = Field(default=None, min_length=1, max_length=20)
    tutor: TutorNuevoSchema | None = None
    parentesco: str = Field(min_length=1, max_length=80)
    es_principal: bool = False
    autorizado: bool = Field(default=True, description="Puede recoger al paciente")

    @model_validator(mode="after")
    def uno_de_dos(self) -> "TutorVincular":
        if (self.id_tutor is None) == (self.tutor is None):
            raise ValueError("Envia id_tutor o tutor (no ambos).")
        return self


class TutorCambios(Entrada):
    parentesco: str | None = Field(default=None, min_length=1, max_length=80)
    es_principal: bool | None = None
    autorizado: bool | None = None
    telefono: str | None = Field(default=None, max_length=30)
    correo: str | None = Field(default=None, max_length=254)
    direccion: str | None = Field(default=None, max_length=300)
    religion: str | None = Field(
        default=None, max_length=100, description="Vacio borra la religion registrada"
    )


class TutorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_tutor: str
    nombres: str
    apellidos: str
    documento: str | None = None
    telefono: str | None = None
    correo: str | None = None
    direccion: str | None = None
    religion: str | None = None


class TutorDePacienteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tutor: TutorResponse
    parentesco: str
    es_principal: bool
    autorizado: bool
