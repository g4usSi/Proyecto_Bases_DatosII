from datetime import datetime
from typing import Protocol

from app.domain.cobros import Cobro, EstadoCobro, NuevoCargo, NuevoPago, Servicio


class RepositorioCobros(Protocol):
    """Cobros de UNA institucion (Hospital General o Centro Pediatrico; los demas: 501).

    Las escrituras se confirman con commit() de la unidad de trabajo. Los totales y el
    "no pagar mas que el saldo" los garantiza la base con bloqueos y triggers.
    """

    def listar_servicios(self) -> list[Servicio]:
        """Catalogo de servicios activos con su tarifa general vigente."""
        ...

    def abrir(
        self,
        id_paciente: str,
        id_atencion: str,
        descripcion: str | None,
        ahora: datetime,
        id_tutor: str | None = None,
    ) -> Cobro:
        """RegistroNoEncontrado si la atencion no es de ese paciente. id_tutor solo aplica
        al Centro Pediatrico (a quien se factura; por defecto el tutor principal)."""
        ...

    def obtener(self, id_paciente: str, id_cobro: str) -> Cobro | None: ...

    def listar(
        self,
        id_paciente: str | None = None,
        estados: frozenset[EstadoCobro] | None = None,
        limite: int = 100,
    ) -> list[Cobro]:
        """Del mas reciente al mas antiguo. Sin id_paciente: toda la institucion."""
        ...

    def agregar_cargo(
        self, id_paciente: str, id_cobro: str, cargo: NuevoCargo, ahora: datetime
    ) -> Cobro:
        """ConflictoEstado si el cobro ya no admite cargos."""
        ...

    def registrar_pago(
        self, id_paciente: str, id_cobro: str, pago: NuevoPago, ahora: datetime
    ) -> Cobro:
        """ConflictoEstado si excede el saldo o el cobro esta anulado."""
        ...

    def anular_pago(self, id_paciente: str, id_cobro: str, id_pago: str) -> Cobro: ...

    def cerrar(self, id_paciente: str, id_cobro: str, ahora: datetime) -> Cobro: ...

    def anular(self, id_paciente: str, id_cobro: str, ahora: datetime) -> Cobro: ...
