from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.consulta import Adenda, Consulta
from app.domain.errores import (
    ConsultaNoEncontrada,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
)
from app.domain.identidad import UsuarioAutenticado


class ConsultarConsulta:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_consulta: str) -> Consulta:
        with self.unidad_trabajo as unidad:
            if unidad.pacientes.obtener_por_id(id_paciente) is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            consulta = unidad.historial.obtener_consulta(id_paciente, id_consulta)
            if consulta is None:
                raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")
            return consulta


class AgregarAConsulta:
    """Agregar diagnostico, tratamiento o receta (o una nota) a una consulta ya guardada.

    Solo agrega: lo guardado no se edita ni se borra. Un error se rectifica con una nota.
    """

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        usuario: UsuarioAutenticado,
        id_paciente: str,
        id_consulta: str,
        adenda: Adenda,
    ) -> Consulta:
        if adenda.vacia:
            raise DatosInvalidos("Agrega al menos un diagnostico, tratamiento, receta o nota.")
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.obtener_por_id(id_paciente)
            if paciente is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if paciente.archivado:
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")
            if unidad.historial.obtener_consulta(id_paciente, id_consulta) is None:
                raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")
            consulta = unidad.historial.agregar_a_consulta(
                id_paciente, id_consulta, usuario.id_usuario, adenda
            )
            unidad.commit()
            return consulta
