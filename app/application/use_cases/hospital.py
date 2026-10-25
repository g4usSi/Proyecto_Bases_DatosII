"""Casos de uso del Hospital General (otros motores responden 501 desde el adaptador)."""

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.hospital import Departamento


class ConsultarDepartamentos:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self) -> list[Departamento]:
        with self.unidad_trabajo as unidad:
            return unidad.hospital.listar_departamentos()
