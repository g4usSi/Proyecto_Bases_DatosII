from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain import busqueda
from app.domain.errores import DatosInvalidos
from app.domain.paciente import Paciente


class BuscarPacientes:
    """Busca pacientes por nombre en el motor de la institucion del usuario."""

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, texto: str, limite: int = 20) -> list[Paciente]:
        buscadas = busqueda.palabras(texto)
        if sum(len(p) for p in buscadas) < busqueda.MIN_LETRAS:
            raise DatosInvalidos(f"Escribe al menos {busqueda.MIN_LETRAS} letras del nombre.")
        if len(buscadas) > busqueda.MAX_PALABRAS or any(
            len(p) > busqueda.MAX_LARGO_PALABRA for p in buscadas
        ):
            raise DatosInvalidos(
                f"Usa como maximo {busqueda.MAX_PALABRAS} palabras de "
                f"{busqueda.MAX_LARGO_PALABRA} letras."
            )
        with self.unidad_trabajo as unidad:
            return unidad.pacientes.buscar(buscadas, limite)
