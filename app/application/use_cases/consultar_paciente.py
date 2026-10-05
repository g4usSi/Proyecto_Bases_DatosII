from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.errores import PacienteNoEncontrado
from app.domain.paciente import Paciente


class ConsultarPaciente:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str) -> Paciente:
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.obtener_por_id(id_paciente)
            if paciente is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            return paciente
