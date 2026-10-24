from datetime import datetime
from typing import Protocol

from app.domain.consulta import Consulta, NuevaConsulta


class RepositorioHistorial(Protocol):
    """Consultas clinicas de UNA institucion."""

    def listar_consultas(
        self, id_paciente: str, limite: int, antes_de: datetime | None = None
    ) -> list[Consulta]:
        """Devuelve consultas de la mas reciente a la mas antigua.

        Paginacion por cursor: `antes_de` es la fecha_hora de la ultima consulta
        recibida. Funciona igual en SQL, MongoDB y Firestore (sin OFFSET costoso).
        """
        ...

    def registrar_consulta(
        self, id_paciente: str, id_profesional: str, datos: NuevaConsulta
    ) -> Consulta:
        """Prepara consulta + diagnosticos + tratamientos + recetas como un todo.

        La escritura debe ser atomica: se confirma completa en commit() o no se guarda.
        """
        ...
