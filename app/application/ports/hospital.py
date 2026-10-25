from datetime import date, datetime
from typing import Protocol

from app.domain.consulta import Diagnostico
from app.domain.hospital import (
    Cama,
    Departamento,
    EstadoCama,
    Ingreso,
    NuevaOrdenMedica,
    NuevoIngreso,
    ResumenHospital,
    TipoIngreso,
)


class RepositorioHospital(Protocol):
    """Modulos propios del Hospital General (los demas motores responden 501).

    Las escrituras se confirman con commit() de la unidad de trabajo. Las reglas de camas
    e ingresos tambien las impone la base (013_camas_ingresos.sql).
    """

    def listar_departamentos(self) -> list[Departamento]:
        """Departamentos (areas) del hospital con conteo de camas, por nombre."""
        ...

    def listar_camas(
        self, id_departamento: int | None = None, estado: EstadoCama | None = None
    ) -> list[Cama]:
        """Camas con su ocupante actual (si lo hay), por departamento y codigo."""
        ...

    def obtener_cama(self, id_cama: int) -> Cama | None: ...

    def cambiar_estado_cama(self, id_cama: int, estado: EstadoCama) -> Cama:
        """ConflictoEstado si la cama tiene un ingreso abierto."""
        ...

    def ingresar(
        self, id_paciente: str, id_profesional: str, datos: NuevoIngreso, ahora: datetime
    ) -> Ingreso:
        """Crea la atencion INGRESO y ocupa la cama. ConflictoEstado si la cama no esta
        disponible o el paciente ya esta ingresado; ProfesionalNoVinculado si la cuenta no
        tiene perfil activo en el hospital."""
        ...

    def obtener_ingreso(self, id_paciente: str, id_ingreso: str) -> Ingreso | None: ...

    def listar_ingresos(
        self,
        id_paciente: str | None = None,
        abiertos: bool | None = None,
        tipo: TipoIngreso | None = None,
        limite: int = 100,
    ) -> list[Ingreso]:
        """Del mas reciente al mas antiguo. Sin id_paciente: todo el hospital (tablero)."""
        ...

    def agregar_diagnostico(
        self, id_paciente: str, id_ingreso: str, diagnostico: Diagnostico
    ) -> Ingreso: ...

    def agregar_orden(
        self,
        id_paciente: str,
        id_ingreso: str,
        id_profesional: str,
        orden: NuevaOrdenMedica,
        ahora: datetime,
    ) -> Ingreso: ...

    def dar_alta(self, id_paciente: str, id_ingreso: str, motivo: str, ahora: datetime) -> Ingreso:
        """Cierra el ingreso (una sola vez) y deja la cama en limpieza."""
        ...

    def resumen(self, hoy: date) -> ResumenHospital:
        """Conteos del dia local `hoy` (ocupacion, ingresos, altas y citas)."""
        ...
