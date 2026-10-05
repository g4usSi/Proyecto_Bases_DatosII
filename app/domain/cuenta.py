from dataclasses import dataclass
from datetime import datetime

from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion


@dataclass(frozen=True, slots=True)
class CuentaProfesional:
    id_profesional: str
    correo: str
    password_hash: str
    institucion: Institucion
    permisos: frozenset[str]
    version_token: int
    activo: bool
    bloqueado_hasta: datetime | None = None

    def usuario(self) -> UsuarioAutenticado:
        return UsuarioAutenticado(self.id_profesional, self.institucion, self.permisos)


@dataclass(frozen=True, slots=True)
class Sesion:
    access_token: str
    expires_in: int
    usuario: UsuarioAutenticado
