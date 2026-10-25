from datetime import datetime
from typing import Protocol

from app.domain.laboratorio import (
    NuevaMuestra,
    Orden,
    PruebaCatalogo,
    Resultado,
)


class RepositorioLaboratorio(Protocol):
    def listar_catalogo(self) -> list[PruebaCatalogo]:
        """Pruebas activas (la version mas reciente de cada una)."""
        ...

    def solicitar(
        self, id_paciente: str, id_consulta: str, id_profesional: str, codigos: tuple[str, ...]
    ) -> Orden:
        """Crea la orden con una copia de cada prueba. DatosInvalidos si un codigo no existe."""
        ...

    def obtener(self, id_paciente: str, id_orden: str) -> Orden | None: ...

    def listar(self, id_paciente: str, limite: int) -> list[Orden]:
        """De la mas reciente a la mas antigua."""
        ...

    def registrar_muestra(
        self, id_paciente: str, id_orden: str, muestra: NuevaMuestra, ahora: datetime
    ) -> Orden: ...

    def registrar_resultados(
        self,
        id_paciente: str,
        id_orden: str,
        codigo_prueba: str,
        resultados: tuple[Resultado, ...],
        observaciones: str | None,
        id_profesional: str,
        ahora: datetime,
    ) -> Orden:
        """Reemplaza los resultados de UNA prueba mientras la orden siga abierta."""
        ...

    def validar(
        self, id_paciente: str, id_orden: str, id_profesional: str, ahora: datetime
    ) -> Orden:
        """Valida la orden. Lanzar ConflictoEstado si ya no esta abierta."""
        ...

    def cancelar(
        self, id_paciente: str, id_orden: str, motivo: str, id_profesional: str, ahora: datetime
    ) -> Orden: ...
