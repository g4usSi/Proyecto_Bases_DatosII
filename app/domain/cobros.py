"""Cobros y pagos: contrato comun del Hospital General (PostgreSQL) y del Centro Pediatrico
(MySQL, "facturacion"). La interfaz no cambia segun el motor; cada uno aplica su modelo:

- Hospital: un cobro por atencion (consulta o ingreso). Cada cargo usa la TARIFA vigente de
  un servicio y la congela; los pagos se anulan (no se borran); estados abierto -> cerrado
  -> pagado, o anulado sin pagos.
- Centro Pediatrico: una factura por consulta. Cada cargo lleva concepto y precio; los
  totales los mantienen triggers. Pagado = saldo cero. No hay cierre ni anulacion.

Los montos son Decimal (en JSON viajan como texto: "150.00") para no perder centavos.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.errores import DatosInvalidos


class EstadoCobro(StrEnum):
    ABIERTO = "abierto"  # admite cargos y pagos
    CERRADO = "cerrado"  # ya no admite cargos; admite pagos
    PAGADO = "pagado"  # saldo cero (final)
    ANULADO = "anulado"  # sin pagos confirmados (final)


class MetodoPago(StrEnum):
    EFECTIVO = "efectivo"
    TARJETA = "tarjeta"
    TRANSFERENCIA = "transferencia"
    CHEQUE = "cheque"


@dataclass(frozen=True, slots=True)
class Servicio:
    id_servicio: int
    nombre: str
    tipo: str
    unidad_cobro: str
    tarifa_general: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Cargo:
    id_cargo: str
    concepto: str
    cantidad: Decimal
    precio_unitario: Decimal
    monto: Decimal
    fecha_hora: datetime
    id_servicio: int | None = None


@dataclass(frozen=True, slots=True)
class Pago:
    id_pago: str
    metodo: MetodoPago
    monto: Decimal
    fecha_hora: datetime
    anulado: bool = False
    referencia: str | None = None


@dataclass(frozen=True, slots=True)
class Cobro:
    id_cobro: str
    id_paciente: str
    nombre_paciente: str
    id_atencion: str  # consulta o ingreso que se cobra
    estado: EstadoCobro
    abierto_en: datetime
    total: Decimal
    pagado: Decimal
    cerrado_en: datetime | None = None
    descripcion: str | None = None
    cargos: tuple[Cargo, ...] = field(default_factory=tuple)
    pagos: tuple[Pago, ...] = field(default_factory=tuple)

    @property
    def saldo(self) -> Decimal:
        return self.total - self.pagado


@dataclass(frozen=True, slots=True)
class NuevoCargo:
    """Hospital: id_servicio (el precio sale de la tarifa). Centro Pediatrico: concepto y precio."""

    cantidad: Decimal
    id_servicio: int | None = None
    concepto: str | None = None
    precio_unitario: Decimal | None = None

    def validar(self) -> None:
        if self.cantidad <= 0:
            raise DatosInvalidos("La cantidad debe ser mayor que cero.")
        if self.precio_unitario is not None and self.precio_unitario < 0:
            raise DatosInvalidos("El precio no puede ser negativo.")
        if self.id_servicio is None and not (self.concepto or "").strip():
            raise DatosInvalidos("Indica el servicio o el concepto del cargo.")


@dataclass(frozen=True, slots=True)
class NuevoPago:
    metodo: MetodoPago
    monto: Decimal
    referencia: str | None = None  # nunca datos de tarjeta

    def validar(self) -> None:
        if self.monto <= 0:
            raise DatosInvalidos("El monto del pago debe ser mayor que cero.")
        if self.monto != self.monto.quantize(Decimal("0.01")):
            raise DatosInvalidos("El monto admite como maximo dos decimales.")
