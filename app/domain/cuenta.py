from dataclasses import dataclass
from datetime import datetime

from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion


@dataclass(frozen=True, slots=True)
class CuentaProfesional:
    id_profesional: str
    correo: str
    password_hash: str
    institucion: Institucion | None
    permisos: frozenset[str]
    version_token: int
    activo: bool
    bloqueado_hasta: datetime | None = None
    nombres: str | None = None
    apellidos: str | None = None
    rol: str | None = None
    debe_cambiar_contrasena: bool = False

    @property
    def es_plataforma(self) -> bool:
        return self.institucion is None

    def usuario(self) -> UsuarioAutenticado:
        return UsuarioAutenticado(
            self.id_profesional,
            self.institucion,
            self.permisos,
            self.nombres,
            self.apellidos,
            self.rol,
            self.debe_cambiar_contrasena,
        )


@dataclass(frozen=True, slots=True)
class Sesion:
    access_token: str
    expires_in: int
    usuario: UsuarioAutenticado
