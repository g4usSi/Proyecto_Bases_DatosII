from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.cobros import EstadoCobro, MetodoPago
from app.presentation.api.schemas.historial import Entrada


class ServicioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_servicio: int
    nombre: str
    tipo: str
    unidad_cobro: str
    tarifa_general: Decimal | None = None


class CobroCrear(Entrada):
    id_atencion: str = Field(
        min_length=1,
        max_length=128,
        description=(
            "Hospital: id de la consulta o del ingreso. Centro Pediatrico: id de la consulta."
        ),
    )
    descripcion: str | None = Field(default=None, max_length=300)
    id_tutor: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        pattern=r"^\d+$",
        description="Solo Centro Pediatrico: tutor a cuyo nombre se factura (vinculado al "
        "paciente). Si se omite, el tutor principal. En el hospital enviarlo es 422.",
    )


class CargoCrear(Entrada):
    """Hospital: id_servicio (precio de la tarifa vigente). Centro Pediatrico: concepto y precio."""

    cantidad: Decimal = Field(default=Decimal(1), gt=0, max_digits=10, decimal_places=2)
    id_servicio: int | None = Field(default=None, ge=1)
    concepto: str | None = Field(default=None, min_length=1, max_length=200)
    precio_unitario: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)


class PagoCrear(Entrada):
    metodo: MetodoPago
    monto: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    referencia: str | None = Field(
        default=None, max_length=150, description="Comprobante; nunca datos de tarjeta."
    )


class CargoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_cargo: str
    concepto: str
    cantidad: Decimal
    precio_unitario: Decimal
    monto: Decimal
    fecha_hora: datetime
    id_servicio: int | None = None


class PagoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_pago: str
    metodo: MetodoPago
    monto: Decimal
    fecha_hora: datetime
    anulado: bool
    referencia: str | None = None


class TitularResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_tutor: str
    nombre: str


class CobroResponse(BaseModel):
    """Los montos viajan como texto decimal ("150.00") para no perder centavos."""

    model_config = ConfigDict(from_attributes=True)

    id_cobro: str
    id_paciente: str
    nombre_paciente: str
    id_atencion: str
    estado: EstadoCobro
    abierto_en: datetime
    cerrado_en: datetime | None = None
    descripcion: str | None = None
    facturado_a: TitularResponse | None = Field(
        default=None, description="Centro Pediatrico: tutor a cuyo nombre esta la factura."
    )
    total: Decimal
    pagado: Decimal
    saldo: Decimal
    cargos: list[CargoResponse]
    pagos: list[PagoResponse]
