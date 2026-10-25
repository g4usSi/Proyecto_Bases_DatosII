"""Agenda de citas. La secretaria agenda; el odontologo marca atendida/no asistio."""

from datetime import UTC, datetime, timedelta

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.cita import TRANSICIONES, Cita, EstadoCita, NuevaCita
from app.domain.errores import (
    CitaNoEncontrada,
    ConflictoAgenda,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
)
from app.domain.identidad import UsuarioAutenticado

RANGO_MAXIMO_AGENDA = timedelta(days=31)


class AgendarCita:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, usuario: UsuarioAutenticado, datos: NuevaCita) -> Cita:
        if datos.inicio <= datetime.now(UTC):
            raise DatosInvalidos("La cita debe agendarse en una fecha y hora futura.")
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.obtener_por_id(datos.id_paciente)
            if paciente is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if paciente.archivado:
                raise PacienteArchivado("El historial esta archivado; no admite citas nuevas.")
            profesional = unidad.profesionales.obtener(datos.id_profesional)
            if profesional is None or not profesional.atiende_pacientes:
                raise DatosInvalidos("El profesional no existe, no esta activo o no atiende.")
            cita = unidad.citas.agendar(
                datos, f"{paciente.nombres} {paciente.apellidos}", usuario.id_usuario
            )
            unidad.commit()
            return cita


class ConsultarAgenda:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self, desde: datetime, hasta: datetime, id_profesional: str | None = None
    ) -> list[Cita]:
        if hasta <= desde:
            raise DatosInvalidos("'hasta' debe ser posterior a 'desde'.")
        if hasta - desde > RANGO_MAXIMO_AGENDA:
            raise DatosInvalidos("La agenda se consulta en rangos de hasta 31 dias.")
        with self.unidad_trabajo as unidad:
            return unidad.citas.listar_agenda(desde, hasta, id_profesional)


class CitasDePaciente:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, limite: int = 50) -> list[Cita]:
        with self.unidad_trabajo as unidad:
            if unidad.pacientes.obtener_por_id(id_paciente) is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            return unidad.citas.listar_por_paciente(id_paciente, limite)


class CambiarEstadoCita:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        usuario: UsuarioAutenticado,
        id_cita: str,
        estado: EstadoCita,
        motivo: str | None = None,
    ) -> Cita:
        if estado == EstadoCita.CANCELADA and not motivo:
            raise DatosInvalidos("Para cancelar una cita indica el motivo.")
        with self.unidad_trabajo as unidad:
            actual = unidad.citas.obtener(id_cita)
            if actual is None:
                raise CitaNoEncontrada("La cita no existe en tu institucion.")
            if estado not in TRANSICIONES.get(actual.estado, set()):
                raise ConflictoAgenda(f"Una cita '{actual.estado}' no puede pasar a '{estado}'.")
            if estado in (EstadoCita.ATENDIDA, EstadoCita.NO_ASISTIO) and actual.inicio > (
                datetime.now(UTC)
            ):
                raise DatosInvalidos("Solo se marca atendida o no asistio despues de su hora.")
            # El adaptador vuelve a comprobar el estado dentro de su transaccion.
            cita = unidad.citas.cambiar_estado(id_cita, estado, usuario.id_usuario, motivo)
            unidad.commit()
            return cita
