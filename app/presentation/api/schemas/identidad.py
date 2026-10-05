from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.domain.institucion import Institucion


class UsuarioResponse(BaseModel):
    id_usuario: str
    institucion: Institucion
    permisos: list[str]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correo: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("correo")
    @classmethod
    def normalizar_correo(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or any(char.isspace() for char in value):
            raise ValueError("Correo invalido.")
        return value


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioResponse
