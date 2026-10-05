from dataclasses import dataclass
from types import TracebackType
from typing import Literal, Self

from app.domain.errores import TokenInvalido
from app.domain.identidad import UsuarioAutenticado
from app.domain.paciente import Paciente


@dataclass
class AutenticadorDoble:
    usuarios: dict[str, UsuarioAutenticado]

    def verificar_token(self, token: str) -> UsuarioAutenticado:
        usuario = self.usuarios.get(token)
        if usuario is None:
            raise TokenInvalido("Token de prueba invalido.")
        return usuario


@dataclass
class RepositorioDoble:
    registros: dict[str, Paciente]

    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        return self.registros.get(id_paciente)


class UnidadTrabajoDoble:
    def __init__(self, registros: dict[str, Paciente]) -> None:
        self.pacientes = RepositorioDoble(registros)
        self.confirmaciones = 0
        self.reversiones = 0
        self.finalizada = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        self.rollback()
        self.finalizada = True
        return False

    def commit(self) -> None:
        self.confirmaciones += 1

    def rollback(self) -> None:
        self.reversiones += 1
