from typing import Protocol

from app.domain.profesional import ProfesionalLocal


class RepositorioProfesionales(Protocol):
    def obtener(self, id_profesional: str) -> ProfesionalLocal | None:
        """Perfil local del profesional en la base clinica de la institucion."""
        ...

    def sincronizar(self, perfil: ProfesionalLocal) -> None:
        """Crea o actualiza el perfil local (nombres, rol, activo) sin correo ni contrasena.

        Idempotente. Se confirma con commit() de la unidad de trabajo.
        """
        ...
