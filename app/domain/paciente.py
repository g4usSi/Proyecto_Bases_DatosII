from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Contacto:
    telefono: str | None = None
    correo: str | None = None
    direccion: str | None = None


@dataclass(frozen=True, slots=True)
class Alergia:
    sustancia: str
    reaccion: str | None = None
    severidad: str | None = None


@dataclass(frozen=True, slots=True)
class Paciente:
    """Contrato comun de lectura.

    Cada adaptador convierte su identificador nativo a texto. El identificador
    solo tiene significado dentro de la institucion del usuario.

    Decision del equipo: no todos los motores guardan todos los datos. `contacto`
    y `alergias` son opcionales; un motor que no los registra devuelve None.
    """

    id_paciente: str
    nombres: str
    apellidos: str
    fecha_nacimiento: date | None = None
    # TODO(cada motor): mapear el estado real. Mientras un adaptador no lo lea,
    # devuelve False y el caso de uso no podra impedir operaciones sobre archivados.
    archivado: bool = False
    contacto: Contacto | None = None
    # None = alergias NO evaluadas (o el motor no las guarda).
    # () = evaluadas, sin alergias conocidas. No son lo mismo clinicamente.
    alergias: tuple[Alergia, ...] | None = None
    grupo_sanguineo: str | None = None


@dataclass(frozen=True, slots=True)
class NuevoPaciente:
    """Datos para abrir un historial. Solo nombres y apellidos son obligatorios."""

    nombres: str
    apellidos: str
    fecha_nacimiento: date | None = None
    contacto: Contacto | None = None
    alergias: tuple[Alergia, ...] | None = field(default=None)


@dataclass(frozen=True, slots=True)
class CambiosPaciente:
    """Correcciones de datos demograficos. None = no cambia.

    `contacto` reemplaza el contacto completo: lo que no se envie queda vacio.
    No incluye alergias (se agregan aparte) ni el estado del historial (se archiva aparte).
    """

    nombres: str | None = None
    apellidos: str | None = None
    fecha_nacimiento: date | None = None
    contacto: Contacto | None = None

    @property
    def vacio(self) -> bool:
        return (
            self.nombres is None
            and self.apellidos is None
            and self.fecha_nacimiento is None
            and self.contacto is None
        )


class MotivoBaja(StrEnum):
    """Causas de archivo indicadas en el enunciado del curso."""

    TRASLADO = "traslado"
    FALLECIMIENTO = "fallecimiento"
    ADMINISTRATIVO = "administrativo"


@dataclass(frozen=True, slots=True)
class Baja:
    """Archivo del historial. No se borra informacion clinica: solo cambia su estado."""

    motivo: MotivoBaja
    id_profesional: str
    fecha: datetime
    detalle: str | None = None
