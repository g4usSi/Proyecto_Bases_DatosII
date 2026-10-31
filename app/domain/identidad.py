from dataclasses import dataclass, field

from app.domain.errores import AccesoDenegado
from app.domain.institucion import Institucion


@dataclass(frozen=True, slots=True)
class UsuarioAutenticado:
    """La institucion y los permisos provienen de una identidad verificada.

    `institucion` es None solo para el superusuario de plataforma: no pertenece a ninguna
    entidad y nunca abre un motor clinico.
    """

    id_usuario: str
    institucion: Institucion | None
    permisos: frozenset[str] = field(default_factory=frozenset)
    # Datos de perfil para /auth/me (opcionales: los dobles de prueba no los necesitan).
    nombres: str | None = None
    apellidos: str | None = None
    rol: str | None = None
    debe_cambiar_contrasena: bool = False

    @property
    def es_plataforma(self) -> bool:
        return self.institucion is None

    def exigir_permiso(self, permiso: str) -> None:
        if permiso not in self.permisos:
            raise AccesoDenegado("No tienes permiso para realizar esta operacion.")
