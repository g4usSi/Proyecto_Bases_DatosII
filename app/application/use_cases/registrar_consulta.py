from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.consulta import Consulta, NuevaConsulta
from app.domain.errores import PacienteArchivado, PacienteNoEncontrado
from app.domain.identidad import UsuarioAutenticado


class RegistrarConsulta:
    """Registrar consulta, agregar diagnosticos y recetar en una sola operacion atomica."""

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self, usuario: UsuarioAutenticado, id_paciente: str, datos: NuevaConsulta
    ) -> Consulta:
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.obtener_por_id(id_paciente)
            if paciente is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if paciente.archivado:
                raise PacienteArchivado("El historial esta archivado; no admite consultas nuevas.")
            # El profesional sale del token verificado, nunca del cuerpo de la solicitud.
            consulta = unidad.historial.registrar_consulta(id_paciente, usuario.id_usuario, datos)
            unidad.commit()
            return consulta
