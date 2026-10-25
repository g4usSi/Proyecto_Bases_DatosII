"""Atencion clinica comun: consulta + diagnosticos + tratamientos + recetas.

Los nombres de campos siguen la coleccion `consultas` del laboratorio (MongoDB),
documentada como contrato comun de los cuatro establecimientos. Una consulta con
sus diagnosticos, tratamientos y recetas se guarda como UNA operacion atomica:
no puede quedar un diagnostico a medias.
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Diagnostico:
    descripcion: str
    codigo: str | None = None  # p. ej. codigo CIE-10, si el equipo decide usarlo
    sistema_codigo: str | None = None  # p. ej. "CIE-10"


@dataclass(frozen=True, slots=True)
class Tratamiento:
    descripcion: str


@dataclass(frozen=True, slots=True)
class Receta:
    medicamento: str
    dosis: str
    frecuencia: str
    via_administracion: str | None = None
    duracion_dias: int | None = None
    instrucciones: str | None = None


@dataclass(frozen=True, slots=True)
class NuevaConsulta:
    motivo: str
    notas: str | None = None
    diagnosticos: tuple[Diagnostico, ...] = field(default_factory=tuple)
    tratamientos: tuple[Tratamiento, ...] = field(default_factory=tuple)
    recetas: tuple[Receta, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Consulta:
    id_consulta: str
    id_paciente: str
    id_profesional: str
    fecha_hora: datetime
    motivo: str
    notas: str | None = None
    diagnosticos: tuple[Diagnostico, ...] = field(default_factory=tuple)
    tratamientos: tuple[Tratamiento, ...] = field(default_factory=tuple)
    recetas: tuple[Receta, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class Adenda:
    """Material que se AGREGA a una consulta ya guardada (nunca reemplaza ni borra).

    Es la forma de "agregar un diagnostico" o "recetar un medicamento" despues de la
    consulta, y tambien de rectificar: un error se aclara con una `nota`, no se edita.
    Quien agrega y cuando queda anotado en las notas de la consulta (ver `rotular`).
    """

    nota: str | None = None
    diagnosticos: tuple[Diagnostico, ...] = field(default_factory=tuple)
    tratamientos: tuple[Tratamiento, ...] = field(default_factory=tuple)
    recetas: tuple[Receta, ...] = field(default_factory=tuple)

    @property
    def vacia(self) -> bool:
        return not (self.nota or self.diagnosticos or self.tratamientos or self.recetas)

    def rotular(self, fecha: datetime, id_profesional: str) -> str:
        """Linea que se anexa a las notas de la consulta, igual en los cuatro motores."""
        partes = []
        for cantidad, singular, plural in (
            (len(self.diagnosticos), "diagnostico", "diagnosticos"),
            (len(self.tratamientos), "tratamiento", "tratamientos"),
            (len(self.recetas), "receta", "recetas"),
        ):
            if cantidad:
                partes.append(f"{cantidad} {singular if cantidad == 1 else plural}")
        resumen = f" Se agregaron: {', '.join(partes)}." if partes else ""
        nota = f" Nota: {self.nota}" if self.nota else ""
        return f"[Adenda {fecha:%Y-%m-%d %H:%M} UTC, profesional {id_profesional}]{resumen}{nota}"
