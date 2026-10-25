"""Hospital General: infraestructura (departamentos, camas) e ingresos hospitalarios."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Departamento:
    id_departamento: int
    nombre: str
