from datetime import UTC, datetime

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.errores import PacienteArchivado, PacienteNoEncontrado
from app.domain.identidad import UsuarioAutenticado
from app.domain.paciente import Baja, MotivoBaja


class ArchivarPaciente:
    """Baja del paciente (traslado, fallecimiento u otra causa). No borra datos."""

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        usuario: UsuarioAutenticado,
        id_paciente: str,
        motivo: MotivoBaja,
        detalle: str | None = None,
    ) -> Baja:
        baja = Baja(motivo, usuario.id_usuario, datetime.now(UTC), detalle)
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.obtener_por_id(id_paciente)
            if paciente is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if paciente.archivado:
                raise PacienteArchivado("El historial ya estaba archivado.")
            unidad.pacientes.archivar(id_paciente, baja)
            unidad.commit()
            return baja
