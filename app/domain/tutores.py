"""Tutores del paciente (Centro Pediatrico): responsables legales y quienes pueden recogerlo.

Un tutor puede estar vinculado a varios pacientes (hermanos). Cada paciente tiene como
maximo un tutor principal, y el principal siempre esta autorizado. Nada se borra: quien ya
no puede recoger al paciente queda como no autorizado.

La religion es opcional y es un dato del tutor (no del vinculo); la base la guarda en su
catalogo `religion`, asi "Catolica" y "catolica" quedan como una sola.
"""

from dataclasses import dataclass

from app.domain.errores import DatosInvalidos


@dataclass(frozen=True, slots=True)
class Tutor:
    id_tutor: str
    nombres: str
    apellidos: str
    documento: str | None = None  # DPI o pasaporte
    telefono: str | None = None
    correo: str | None = None
    direccion: str | None = None
    religion: str | None = None


@dataclass(frozen=True, slots=True)
class TutorDePaciente:
    tutor: Tutor
    parentesco: str
    es_principal: bool
    autorizado: bool  # puede recoger al paciente


@dataclass(frozen=True, slots=True)
class NuevoTutor:
    nombres: str
    apellidos: str
    documento: str | None = None
    telefono: str | None = None
    correo: str | None = None
    direccion: str | None = None
    religion: str | None = None


@dataclass(frozen=True, slots=True)
class Vinculo:
    parentesco: str
    es_principal: bool = False
    autorizado: bool = True

    def validar(self) -> None:
        if not self.parentesco.strip():
            raise DatosInvalidos("Indica el parentesco.")
        if self.es_principal and not self.autorizado:
            raise DatosInvalidos("El tutor principal debe estar autorizado.")


@dataclass(frozen=True, slots=True)
class CambiosTutor:
    """None = no cambia; "" borra el dato. El contacto y la religion son del tutor (se ven en
    todos sus pacientes)."""

    parentesco: str | None = None
    es_principal: bool | None = None
    autorizado: bool | None = None
    telefono: str | None = None
    correo: str | None = None
    direccion: str | None = None
    religion: str | None = None

    @property
    def vacio(self) -> bool:
        return all(
            v is None
            for v in (
                self.parentesco,
                self.es_principal,
                self.autorizado,
                self.telefono,
                self.correo,
                self.direccion,
                self.religion,
            )
        )


def nombre_de_religion(texto: str | None) -> str | None:
    """Normaliza el nombre de la religion: sin espacios de mas; vacio = sin religion."""
    if texto is None:
        return None
    limpio = " ".join(texto.split())
    return limpio or None
