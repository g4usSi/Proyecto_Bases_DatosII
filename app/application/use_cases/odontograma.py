from datetime import UTC, datetime

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.errores import DatosInvalidos, PacienteArchivado, PacienteNoEncontrado
from app.domain.identidad import UsuarioAutenticado
from app.domain.odontograma import (
    EstadoDental,
    EstadoPieza,
    Odontograma,
    Superficie,
    es_pieza_valida,
)


class ConsultarOdontograma:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str) -> Odontograma:
        with self.unidad_trabajo as unidad:
            if unidad.pacientes.obtener_por_id(id_paciente) is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            return unidad.odontograma.obtener(id_paciente)


class ActualizarPieza:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        usuario: UsuarioAutenticado,
        id_paciente: str,
        pieza: str,
        estado: EstadoDental,
        superficies: tuple[Superficie, ...] = (),
        nota: str | None = None,
    ) -> EstadoPieza:
        if not es_pieza_valida(pieza):
            raise DatosInvalidos(f"'{pieza}' no es una pieza dental valida (numeracion FDI).")
        nuevo = EstadoPieza(pieza, estado, usuario.id_usuario, datetime.now(UTC), superficies, nota)
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.obtener_por_id(id_paciente)
            if paciente is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if paciente.archivado:
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")
            unidad.odontograma.actualizar_pieza(id_paciente, nuevo)
            unidad.commit()
            return nuevo
