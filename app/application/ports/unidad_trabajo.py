from types import TracebackType
from typing import Literal, Protocol, Self

from app.application.ports.citas import RepositorioCitas
from app.application.ports.historial import RepositorioHistorial
from app.application.ports.hospital import RepositorioHospital
from app.application.ports.laboratorio import RepositorioLaboratorio
from app.application.ports.odontograma import RepositorioOdontograma
from app.application.ports.pacientes import RepositorioPacientes
from app.application.ports.pediatria import RepositorioCrecimiento, RepositorioVacunacion
from app.application.ports.profesionales import RepositorioProfesionales


class UnidadDeTrabajo(Protocol):
    """Una operacion de negocio utiliza una unidad de trabajo por solicitud.

    Los adaptadores deben revertir los cambios no confirmados al salir y liberar
    sus recursos. Los casos de uso de escritura llaman a commit explicitamente.
    Un motor que no implementa un repositorio usa las piezas de
    infrastructure/persistence/pendiente.py (HTTP 501).
    """

    @property
    def pacientes(self) -> RepositorioPacientes: ...

    @property
    def historial(self) -> RepositorioHistorial: ...

    @property
    def profesionales(self) -> RepositorioProfesionales: ...

    @property
    def citas(self) -> RepositorioCitas: ...

    @property
    def odontograma(self) -> RepositorioOdontograma: ...

    @property
    def crecimiento(self) -> RepositorioCrecimiento: ...

    @property
    def vacunacion(self) -> RepositorioVacunacion: ...

    @property
    def laboratorio(self) -> RepositorioLaboratorio: ...

    @property
    def hospital(self) -> RepositorioHospital: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False] | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
