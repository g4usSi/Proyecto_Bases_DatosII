from datetime import date, datetime
from typing import Protocol

from app.domain.pediatria import (
    ControlCrecimiento,
    DescripcionVacuna,
    DosisVacuna,
    NuevoControl,
    TipoVacuna,
)


class RepositorioCrecimiento(Protocol):
    def registrar(
        self, id_paciente: str, datos: NuevoControl, fecha: datetime, edad_meses: int | None
    ) -> ControlCrecimiento:
        """Agrega un control. Los controles no se editan ni se borran."""
        ...

    def listar(self, id_paciente: str, limite: int) -> list[ControlCrecimiento]:
        """De mas reciente a mas antiguo."""
        ...


class RepositorioVacunacion(Protocol):
    def listar_tipos(self) -> list[TipoVacuna]: ...

    def agregar_tipo(self, nombre: str, descripcion: DescripcionVacuna) -> TipoVacuna:
        """Agrega una vacuna al catalogo. ConflictoEstado si el nombre ya existe."""
        ...

    def describir_tipo(self, id_vacuna: str, descripcion: DescripcionVacuna) -> TipoVacuna:
        """Reemplaza la descripcion (no el nombre). RegistroNoEncontrado si no existe."""
        ...

    def listar_esquema(self, id_paciente: str) -> list[DosisVacuna]: ...

    def obtener_dosis(self, id_paciente: str, id_dosis: str) -> DosisVacuna | None: ...

    def programar(
        self,
        id_paciente: str,
        id_vacuna: str,
        numero_dosis: int | None,
        fecha_programada: date | None,
    ) -> DosisVacuna: ...

    def aplicar(
        self,
        id_paciente: str,
        id_dosis: str,
        id_profesional: str,
        fecha: datetime,
        observaciones: str | None,
    ) -> DosisVacuna:
        """Aplica una dosis pendiente (quien, cuando, observaciones). No maneja lotes ni stock.

        Lanzar RegistroNoEncontrado o ConflictoEstado (la dosis no estaba pendiente).
        """
        ...

    def cancelar(self, id_paciente: str, id_dosis: str) -> DosisVacuna: ...
