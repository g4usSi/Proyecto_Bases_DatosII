from types import TracebackType
from typing import Literal, Protocol, Self

from app.application.ports.pacientes import RepositorioPacientes


class UnidadDeTrabajo(Protocol):
    """Una operacion de negocio utiliza una unidad de trabajo por solicitud.

    Los adaptadores deben revertir los cambios no confirmados al salir y liberar
    sus recursos. Los casos de uso de escritura llamaran a commit explicitamente.
    """

    @property
    def pacientes(self) -> RepositorioPacientes: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False] | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
