from datetime import date

from pydantic import BaseModel, ConfigDict


class PacienteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_paciente: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date | None = None
