"""Tutores del paciente (Centro Pediatrico)."""

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.errores import (
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    RegistroNoEncontrado,
)
from app.domain.tutores import CambiosTutor, NuevoTutor, Tutor, TutorDePaciente, Vinculo


def _paciente(unidad: UnidadDeTrabajo, id_paciente: str, activo: bool) -> None:
    paciente = unidad.pacientes.obtener_por_id(id_paciente)
    if paciente is None:
        raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
    if activo and paciente.archivado:
        raise PacienteArchivado("El historial esta archivado; no admite cambios.")


class ConsultarTutores:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def del_paciente(self, id_paciente: str) -> list[TutorDePaciente]:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, activo=False)
            return unidad.tutores.listar(id_paciente)

    def por_documento(self, documento: str) -> Tutor:
        if not documento.strip():
            raise DatosInvalidos("Indica el documento.")
        with self.unidad_trabajo as unidad:
            tutor = unidad.tutores.buscar_por_documento(documento.strip())
        if tutor is None:
            raise RegistroNoEncontrado("No hay un tutor con ese documento.")
        return tutor

    def religiones(self) -> list[str]:
        with self.unidad_trabajo as unidad:
            return unidad.tutores.listar_religiones()


class VincularTutor:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        id_paciente: str,
        vinculo: Vinculo,
        id_tutor: str | None = None,
        nuevo: NuevoTutor | None = None,
    ) -> TutorDePaciente:
        if (id_tutor is None) == (nuevo is None):
            raise DatosInvalidos("Envia id_tutor (tutor existente) o los datos del tutor nuevo.")
        vinculo.validar()
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, activo=True)
            resultado = unidad.tutores.vincular(id_paciente, vinculo, id_tutor, nuevo)
            unidad.commit()
            return resultado


class CambiarTutor:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_tutor: str, cambios: CambiosTutor) -> TutorDePaciente:
        if cambios.vacio:
            raise DatosInvalidos("No enviaste ningun cambio.")
        if cambios.es_principal and cambios.autorizado is False:
            raise DatosInvalidos("El tutor principal debe estar autorizado.")
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, activo=True)
            resultado = unidad.tutores.cambiar(id_paciente, id_tutor, cambios)
            unidad.commit()
            return resultado
