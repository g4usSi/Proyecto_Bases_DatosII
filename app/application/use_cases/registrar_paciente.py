from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.paciente import NuevoPaciente, Paciente


class RegistrarPaciente:
    """Abre un historial nuevo en el motor de la institucion del usuario."""

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, datos: NuevoPaciente) -> Paciente:
        # PENDIENTE DE ACORDAR: regla de duplicados (mismo documento/expediente).
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.registrar(datos)
            unidad.commit()
            return paciente
