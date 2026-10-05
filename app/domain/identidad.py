from dataclasses import dataclass, field

from app.domain.errores import AccesoDenegado
from app.domain.institucion import Institucion


@dataclass(frozen=True, slots=True)
class UsuarioAutenticado:
    """La institucion y los permisos provienen de una identidad verificada."""

    id_usuario: str
    institucion: Institucion
    permisos: frozenset[str] = field(default_factory=frozenset)

    def exigir_permiso(self, permiso: str) -> None:
        if permiso not in self.permisos:
            raise AccesoDenegado("No tienes permiso para realizar esta operacion.")
