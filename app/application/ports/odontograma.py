from typing import Protocol

from app.domain.odontograma import EstadoPieza, Odontograma


class RepositorioOdontograma(Protocol):
    def obtener(self, id_paciente: str) -> Odontograma:
        """Estado actual de las piezas; vacio si nunca se registro."""
        ...

    def actualizar_pieza(self, id_paciente: str, estado: EstadoPieza) -> None:
        """Reemplaza el estado de una pieza sin tocar las demas."""
        ...
