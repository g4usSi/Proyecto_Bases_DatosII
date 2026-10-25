from typing import Protocol

from app.domain.hospital import Departamento


class RepositorioHospital(Protocol):
    """Modulos propios del Hospital General (los demas motores responden 501)."""

    def listar_departamentos(self) -> list[Departamento]:
        """Departamentos (areas) del hospital, por nombre."""
        ...
