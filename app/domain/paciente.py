from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Paciente:
    """Contrato inicial de lectura; se ampliara con el modelo clinico acordado.

    Cada adaptador convierte su identificador nativo a texto. El identificador
    solo tiene significado dentro de la institucion del usuario.
    """

    id_paciente: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date | None = None
