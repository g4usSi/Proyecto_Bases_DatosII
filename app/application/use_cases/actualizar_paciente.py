from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.busqueda import normalizar
from app.domain.errores import DatosInvalidos, PacienteArchivado, PacienteNoEncontrado
from app.domain.paciente import Alergia, CambiosPaciente, Paciente


class ActualizarPaciente:
    """Corrige datos demograficos de un historial activo (nombre, nacimiento, contacto)."""

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, cambios: CambiosPaciente) -> Paciente:
        if cambios.vacio:
            raise DatosInvalidos("Indica al menos un dato para corregir.")
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.obtener_por_id(id_paciente)
            if paciente is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if paciente.archivado:
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")
            unidad.pacientes.actualizar(id_paciente, cambios)
            unidad.commit()
            actualizado = unidad.pacientes.obtener_por_id(id_paciente)
            return actualizado if actualizado is not None else paciente


class AgregarAlergias:
    """Agrega alergias a un historial activo. No borra ni edita las existentes."""

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, nuevas: tuple[Alergia, ...]) -> Paciente:
        if not nuevas:
            raise DatosInvalidos("Indica al menos una alergia.")
        sustancias = [normalizar(a.sustancia).strip() for a in nuevas]
        if len(sustancias) != len(set(sustancias)):
            raise DatosInvalidos("Una misma alergia no puede repetirse.")
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.obtener_por_id(id_paciente)
            if paciente is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if paciente.archivado:
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")
            existentes = {normalizar(a.sustancia).strip() for a in paciente.alergias or ()}
            repetidas = existentes & set(sustancias)
            if repetidas:
                raise DatosInvalidos("Esa alergia ya estaba registrada.")
            unidad.pacientes.agregar_alergias(id_paciente, nuevas)
            unidad.commit()
            actualizado = unidad.pacientes.obtener_por_id(id_paciente)
            return actualizado if actualizado is not None else paciente
