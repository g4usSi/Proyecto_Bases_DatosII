from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion


class UsuarioResponse(BaseModel):
    id_usuario: str
    institucion: Institucion
    permisos: list[str]
    nombres: str | None = None
    apellidos: str | None = None
    rol: str | None = None
    debe_cambiar_contrasena: bool = Field(
        default=False,
        description="True tras un alta o restablecimiento: pedir que elija su contrasena.",
    )

    @classmethod
    def de(cls, usuario: UsuarioAutenticado) -> "UsuarioResponse":
        return cls(
            id_usuario=usuario.id_usuario,
            institucion=usuario.institucion,
            permisos=sorted(usuario.permisos),
            nombres=usuario.nombres,
            apellidos=usuario.apellidos,
            rol=usuario.rol,
            debe_cambiar_contrasena=usuario.debe_cambiar_contrasena,
        )


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
