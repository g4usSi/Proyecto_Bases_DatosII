from dataclasses import dataclass
from datetime import datetime

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.consulta import Consulta
from app.domain.errores import PacienteNoEncontrado
from app.domain.paciente import Paciente


@dataclass(frozen=True, slots=True)
class Historial:
    paciente: Paciente
    consultas: list[Consulta]
    # Cursor para pedir la pagina siguiente; None si no hay mas.
    siguiente_antes_de: datetime | None


class ConsultarHistorial:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self, id_paciente: str, limite: int = 20, antes_de: datetime | None = None
    ) -> Historial:
        with self.unidad_trabajo as unidad:
            paciente = unidad.pacientes.obtener_por_id(id_paciente)
            if paciente is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            # Se pide uno extra para saber si existe otra pagina.
            consultas = unidad.historial.listar_consultas(id_paciente, limite + 1, antes_de)
            hay_mas = len(consultas) > limite
            consultas = consultas[:limite]
            siguiente = consultas[-1].fecha_hora if hay_mas and consultas else None
            return Historial(paciente, consultas, siguiente)
