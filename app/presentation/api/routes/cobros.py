"""Cobros y pagos: Hospital General y Centro Pediatrico (otros establecimientos: 501).

Ver montos exige pagos:ver; abrir, cargar, pagar, anular o cerrar exige pagos:registrar.
La administracion general (superusuario) solo lee: elige la entidad con
`?establecimiento=` y cualquier escritura le responde 403.
"""

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.application.use_cases.cobros import (
    AbrirCobro,
    AgregarCargo,
    AnularCobro,
    AnularPago,
    CerrarCobro,
    ConsultarCobros,
    ConsultarServicios,
    RegistrarPago,
)
from app.domain.cobros import EstadoCobro, NuevoCargo, NuevoPago
from app.presentation.api.dependencies import ContextoRegistrarPagos, ContextoVerPagos
from app.presentation.api.schemas.cobros import (
    CargoCrear,
    CobroCrear,
    CobroResponse,
    PagoCrear,
    ServicioResponse,
)

router = APIRouter(tags=["Cobros"])

IdPaciente = Annotated[str, Path(min_length=1, max_length=128)]
IdCobro = Annotated[str, Path(min_length=1, max_length=20)]
IdPago = Annotated[str, Path(min_length=1, max_length=20)]
RUTA = "/pacientes/{id_paciente}/cobros/{id_cobro}"


def _r(cobro) -> CobroResponse:
    return CobroResponse.model_validate(cobro)


@router.get("/servicios", response_model=list[ServicioResponse])
def servicios(contexto: ContextoVerPagos) -> list[ServicioResponse]:
    """Servicios con tarifa general vigente (Hospital General)."""
    return [
        ServicioResponse.model_validate(s) for s in ConsultarServicios(contexto.unidad).ejecutar()
    ]


@router.get("/cobros", response_model=list[CobroResponse])
def tablero_de_cobros(
    contexto: ContextoVerPagos,
    estado: Annotated[list[EstadoCobro] | None, Query(description="Repetible")] = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[CobroResponse]:
    """Cobros de toda tu institucion, mas recientes primero."""
    cobros = ConsultarCobros(contexto.unidad).tablero(frozenset(estado) if estado else None, limite)
    return [_r(c) for c in cobros]


@router.post(
    "/pacientes/{id_paciente}/cobros",
    response_model=CobroResponse,
    status_code=status.HTTP_201_CREATED,
)
def abrir_cobro(
    id_paciente: IdPaciente, datos: CobroCrear, contexto: ContextoRegistrarPagos
) -> CobroResponse:
    """Abre el cobro de una atencion (una por atencion; 409 si ya tiene uno vigente).
    Centro Pediatrico: la factura queda a nombre de `id_tutor` o del tutor principal."""
    return _r(
        AbrirCobro(contexto.unidad).ejecutar(
            id_paciente, datos.id_atencion, datos.descripcion, datos.id_tutor
        )
    )


@router.get("/pacientes/{id_paciente}/cobros", response_model=list[CobroResponse])
def cobros_del_paciente(id_paciente: IdPaciente, contexto: ContextoVerPagos) -> list[CobroResponse]:
    return [_r(c) for c in ConsultarCobros(contexto.unidad).del_paciente(id_paciente)]


@router.get(RUTA, response_model=CobroResponse)
def consultar_cobro(
    id_paciente: IdPaciente, id_cobro: IdCobro, contexto: ContextoVerPagos
) -> CobroResponse:
    return _r(ConsultarCobros(contexto.unidad).uno(id_paciente, id_cobro))


@router.post(RUTA + "/cargos", response_model=CobroResponse)
def agregar_cargo(
    id_paciente: IdPaciente, id_cobro: IdCobro, datos: CargoCrear, contexto: ContextoRegistrarPagos
) -> CobroResponse:
    """Agrega un cargo mientras el cobro este abierto (409 si no)."""
    cargo = NuevoCargo(datos.cantidad, datos.id_servicio, datos.concepto, datos.precio_unitario)
    return _r(AgregarCargo(contexto.unidad).ejecutar(id_paciente, id_cobro, cargo))


@router.post(RUTA + "/pagos", response_model=CobroResponse)
def registrar_pago(
    id_paciente: IdPaciente, id_cobro: IdCobro, datos: PagoCrear, contexto: ContextoRegistrarPagos
) -> CobroResponse:
    """409 si excede el saldo (aunque dos pagos lleguen a la vez) o si el cobro esta anulado.
    Al quedar en saldo cero el cobro pasa a pagado."""
    pago = NuevoPago(datos.metodo, datos.monto, datos.referencia)
    return _r(RegistrarPago(contexto.unidad).ejecutar(id_paciente, id_cobro, pago))


@router.post(RUTA + "/pagos/{id_pago}/anular", response_model=CobroResponse)
def anular_pago(
    id_paciente: IdPaciente, id_cobro: IdCobro, id_pago: IdPago, contexto: ContextoRegistrarPagos
) -> CobroResponse:
    """El pago queda registrado como anulado (no se borra). Solo Hospital General."""
    return _r(AnularPago(contexto.unidad).ejecutar(id_paciente, id_cobro, id_pago))


@router.post(RUTA + "/cerrar", response_model=CobroResponse)
def cerrar_cobro(
    id_paciente: IdPaciente, id_cobro: IdCobro, contexto: ContextoRegistrarPagos
) -> CobroResponse:
    """Ya no admite cargos; si admite pagos. Solo Hospital General."""
    return _r(CerrarCobro(contexto.unidad).ejecutar(id_paciente, id_cobro))


@router.post(RUTA + "/anular", response_model=CobroResponse)
def anular_cobro(
    id_paciente: IdPaciente, id_cobro: IdCobro, contexto: ContextoRegistrarPagos
) -> CobroResponse:
    """Solo sin pagos confirmados (409 si los tiene). Hospital General y Centro Pediatrico:
    la factura queda anulada (no se borra) y ya no admite cargos ni pagos."""
    return _r(AnularCobro(contexto.unidad).ejecutar(id_paciente, id_cobro))
