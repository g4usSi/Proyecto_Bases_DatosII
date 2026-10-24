from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.busqueda import normalizar
from app.domain.errores import DatosInvalidos
from app.domain.paciente import NuevoPaciente, Paciente


class RegistrarPaciente:
    """Abre un historial nuevo en el motor de la institucion del usuario."""

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, datos: NuevoPaciente) -> Paciente:
        # PENDIENTE DE ACORDAR: regla de duplicados (mismo documento/expediente).
        sustancias = [normalizar(a.sustancia).strip() for a in datos.alergias or ()]
        if len(sustancias) != len(set(sustancias)):
            raise DatosInvalidos("Una misma alergia no puede repetirse.")
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.registrar(datos)
            unidad.commit()
            return paciente
