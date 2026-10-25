"""Crecimiento y vacunacion del Centro Pediatrico."""

from datetime import UTC, date, datetime

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.errores import (
    ConflictoEstado,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    RegistroNoEncontrado,
)
from app.domain.identidad import UsuarioAutenticado
from app.domain.paciente import Paciente
from app.domain.pediatria import (
    ControlCrecimiento,
    DosisVacuna,
    EstadoDosis,
    NuevoControl,
    TipoVacuna,
    meses_cumplidos,
    sumar_meses,
)


def _paciente(unidad, id_paciente: str, escribir: bool) -> Paciente:
    paciente = unidad.pacientes.obtener_por_id(id_paciente)
    if paciente is None:
        raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
    if escribir and paciente.archivado:
        raise PacienteArchivado("El historial esta archivado; no admite cambios.")
    return paciente


class RegistrarControlCrecimiento:
    """Agrega un control de crecimiento. La edad en meses se calcula con la fecha de nacimiento."""

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, datos: NuevoControl) -> ControlCrecimiento:
        if datos.vacio:
            raise DatosInvalidos(
                "Registra al menos peso, talla, perimetro cefalico u observaciones."
            )
        ahora = datetime.now(UTC)
        with self.unidad_trabajo as unidad:
            paciente = _paciente(unidad, id_paciente, escribir=True)
            edad = (
                meses_cumplidos(paciente.fecha_nacimiento, ahora.date())
                if paciente.fecha_nacimiento
                else None
            )
            control = unidad.crecimiento.registrar(id_paciente, datos, ahora, edad)
            unidad.commit()
            return control


class ConsultarCrecimiento:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, limite: int = 50) -> list[ControlCrecimiento]:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=False)
            return unidad.crecimiento.listar(id_paciente, limite)


class ConsultarCatalogoVacunas:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def tipos(self) -> list[TipoVacuna]:
        with self.unidad_trabajo as unidad:
            return unidad.vacunacion.listar_tipos()


class ConsultarEsquema:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str) -> list[DosisVacuna]:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=False)
            return unidad.vacunacion.listar_esquema(id_paciente)


class ProgramarDosis:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        id_paciente: str,
        id_vacuna: str,
        numero_dosis: int | None,
        fecha_programada: date | None,
    ) -> DosisVacuna:
        with self.unidad_trabajo as unidad:
            paciente = _paciente(unidad, id_paciente, escribir=True)
            if (
                fecha_programada
                and paciente.fecha_nacimiento
                and fecha_programada < paciente.fecha_nacimiento
            ):
                raise DatosInvalidos("La dosis no puede programarse antes del nacimiento.")
            if numero_dosis is not None:
                repetida = any(
                    d.id_vacuna == id_vacuna
                    and d.numero_dosis == numero_dosis
                    and d.estado != EstadoDosis.CANCELADA
                    for d in unidad.vacunacion.listar_esquema(id_paciente)
                )
                if repetida:
                    raise ConflictoEstado("Esa dosis de esa vacuna ya esta en el esquema.")
            dosis = unidad.vacunacion.programar(
                id_paciente, id_vacuna, numero_dosis, fecha_programada
            )
            unidad.commit()
            return dosis


class GenerarEsquemaRecomendado:
    """Programa la primera dosis de cada vacuna del catalogo con edad recomendada.

    Usa la edad recomendada del catalogo (no inventa calendarios) y omite las vacunas que el
    paciente ya tiene en su esquema, de modo que puede repetirse sin duplicar.
    """

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str) -> list[DosisVacuna]:
        with self.unidad_trabajo as unidad:
            paciente = _paciente(unidad, id_paciente, escribir=True)
            ya = {
                d.id_vacuna
                for d in unidad.vacunacion.listar_esquema(id_paciente)
                if d.estado != EstadoDosis.CANCELADA
            }
            if paciente.fecha_nacimiento is None:
                raise DatosInvalidos("El paciente no tiene fecha de nacimiento registrada.")
            creadas = [
                unidad.vacunacion.programar(
                    id_paciente,
                    tipo.id_vacuna,
                    1,
                    sumar_meses(paciente.fecha_nacimiento, tipo.edad_recomendada_meses),
                )
                for tipo in unidad.vacunacion.listar_tipos()
                if tipo.edad_recomendada_meses is not None and tipo.id_vacuna not in ya
            ]
            unidad.commit()
            return creadas


class AplicarDosis:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        usuario: UsuarioAutenticado,
        id_paciente: str,
        id_dosis: str,
        observaciones: str | None,
    ) -> DosisVacuna:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=True)
            dosis = unidad.vacunacion.obtener_dosis(id_paciente, id_dosis)
            if dosis is None:
                raise RegistroNoEncontrado("La dosis no existe en el esquema del paciente.")
            if dosis.estado != EstadoDosis.PENDIENTE:
                raise ConflictoEstado(f"Una dosis {dosis.estado.value} no puede aplicarse.")
            aplicada = unidad.vacunacion.aplicar(
                id_paciente, id_dosis, usuario.id_usuario, datetime.now(UTC), observaciones
            )
            unidad.commit()
            return aplicada


class CancelarDosis:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_dosis: str) -> DosisVacuna:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=True)
            dosis = unidad.vacunacion.obtener_dosis(id_paciente, id_dosis)
            if dosis is None:
                raise RegistroNoEncontrado("La dosis no existe en el esquema del paciente.")
            if dosis.estado != EstadoDosis.PENDIENTE:
                raise ConflictoEstado(f"Una dosis {dosis.estado.value} no puede cancelarse.")
            cancelada = unidad.vacunacion.cancelar(id_paciente, id_dosis)
            unidad.commit()
            return cancelada
