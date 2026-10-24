from typing import Protocol

from app.domain.profesional import ProfesionalLocal


class RepositorioProfesionales(Protocol):
    def obtener(self, id_profesional: str) -> ProfesionalLocal | None:
        """Perfil local del profesional en la base clinica de la institucion."""
        ...
