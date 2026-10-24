from datetime import datetime
from typing import Protocol

from app.domain.cita import Cita, EstadoCita, NuevaCita


class RepositorioCitas(Protocol):
    def obtener(self, id_cita: str) -> Cita | None: ...

    def agendar(self, datos: NuevaCita, nombre_paciente: str, creada_por: str) -> Cita:
        """Reserva el horario de forma atomica.

        Si el profesional ya tiene una cita programada que se cruza, lanzar
        ConflictoAgenda. La comprobacion y la escritura deben ocurrir en la misma
        transaccion para que dos secretarias no reserven el mismo horario.
        """
        ...

    def listar_agenda(
        self, desde: datetime, hasta: datetime, id_profesional: str | None = None
    ) -> list[Cita]:
        """Citas con inicio en [desde, hasta), ordenadas por inicio."""
        ...

    def listar_por_paciente(self, id_paciente: str, limite: int) -> list[Cita]:
        """Citas del paciente, de la mas reciente a la mas antigua."""
        ...

    def cambiar_estado(
        self, id_cita: str, estado: EstadoCita, por: str, motivo: str | None
    ) -> Cita:
        """Cambia el estado de forma atomica; si se cancela, libera el horario.

        Lanzar CitaNoEncontrada o ConflictoAgenda (cambio no permitido).
        """
        ...
