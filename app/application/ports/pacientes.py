from typing import Protocol

from app.domain.paciente import Paciente


class RepositorioPacientes(Protocol):
    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        """Busca un paciente exclusivamente en la institucion del adaptador."""
        ...
