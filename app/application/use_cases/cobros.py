"""Cobros y pagos (Hospital General y Centro Pediatrico). Nada se borra: un error se
corrige anulando el pago o el cobro, nunca editandolo."""

from datetime import UTC, datetime

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.cobros import Cobro, EstadoCobro, NuevoCargo, NuevoPago, Servicio
from app.domain.errores import PacienteNoEncontrado, RegistroNoEncontrado


def _paciente(unidad: UnidadDeTrabajo, id_paciente: str) -> None:
    # Se puede cobrar a un historial archivado (p. ej. la estancia previa a un traslado).
    if unidad.pacientes.obtener_por_id(id_paciente) is None:
        raise PacienteNoEncontrado("El paciente no existe en tu institucion.")


def _existe(unidad: UnidadDeTrabajo, id_paciente: str, id_cobro: str) -> None:
    _paciente(unidad, id_paciente)
    if unidad.cobros.obtener(id_paciente, id_cobro) is None:
        raise RegistroNoEncontrado("El cobro no existe para ese paciente.")


class ConsultarServicios:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self) -> list[Servicio]:
        with self.unidad_trabajo as unidad:
            return unidad.cobros.listar_servicios()


class ConsultarCobros:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def tablero(
        self, estados: frozenset[EstadoCobro] | None = None, limite: int = 100
    ) -> list[Cobro]:
        with self.unidad_trabajo as unidad:
            return unidad.cobros.listar(None, estados, limite)

    def del_paciente(self, id_paciente: str, limite: int = 100) -> list[Cobro]:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente)
            return unidad.cobros.listar(id_paciente, None, limite)

    def uno(self, id_paciente: str, id_cobro: str) -> Cobro:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente)
            cobro = unidad.cobros.obtener(id_paciente, id_cobro)
            if cobro is None:
                raise RegistroNoEncontrado("El cobro no existe para ese paciente.")
            return cobro


class AbrirCobro:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        id_paciente: str,
        id_atencion: str,
        descripcion: str | None,
        id_tutor: str | None = None,
    ) -> Cobro:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente)
            cobro = unidad.cobros.abrir(
                id_paciente, id_atencion, descripcion, datetime.now(UTC), id_tutor
            )
            unidad.commit()
            return cobro


class AgregarCargo:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_cobro: str, cargo: NuevoCargo) -> Cobro:
        cargo.validar()
        with self.unidad_trabajo as unidad:
            _existe(unidad, id_paciente, id_cobro)
            cobro = unidad.cobros.agregar_cargo(id_paciente, id_cobro, cargo, datetime.now(UTC))
            unidad.commit()
            return cobro


class RegistrarPago:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_cobro: str, pago: NuevoPago) -> Cobro:
        pago.validar()
        with self.unidad_trabajo as unidad:
            _existe(unidad, id_paciente, id_cobro)
            cobro = unidad.cobros.registrar_pago(id_paciente, id_cobro, pago, datetime.now(UTC))
            unidad.commit()
            return cobro


class AnularPago:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_cobro: str, id_pago: str) -> Cobro:
        with self.unidad_trabajo as unidad:
            _existe(unidad, id_paciente, id_cobro)
            cobro = unidad.cobros.anular_pago(id_paciente, id_cobro, id_pago)
            unidad.commit()
            return cobro


class CerrarCobro:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_cobro: str) -> Cobro:
        with self.unidad_trabajo as unidad:
            _existe(unidad, id_paciente, id_cobro)
            cobro = unidad.cobros.cerrar(id_paciente, id_cobro, datetime.now(UTC))
            unidad.commit()
            return cobro


class AnularCobro:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_cobro: str) -> Cobro:
        with self.unidad_trabajo as unidad:
            _existe(unidad, id_paciente, id_cobro)
            cobro = unidad.cobros.anular(id_paciente, id_cobro, datetime.now(UTC))
            unidad.commit()
            return cobro
