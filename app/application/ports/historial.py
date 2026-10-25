from datetime import datetime
from typing import Protocol

from app.domain.consulta import Adenda, Consulta, NuevaConsulta


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

    def obtener_consulta(self, id_paciente: str, id_consulta: str) -> Consulta | None:
        """Una consulta con todo lo que tiene, o None si no es de ese paciente."""
        ...

    def agregar_a_consulta(
        self, id_paciente: str, id_consulta: str, id_profesional: str, adenda: Adenda
    ) -> Consulta:
        """Agrega diagnosticos, tratamientos, recetas y/o una nota a una consulta existente.

        Solo agrega: no modifica ni borra lo ya guardado. Es atomica (todo o nada) y se
        confirma en commit(). Debe anexar `adenda.rotular(...)` a las notas de la consulta.
        Lanzar ConsultaNoEncontrada, PacienteArchivado o DatosInvalidos segun corresponda.
        Devuelve la consulta completa y actualizada.
        """
        ...
