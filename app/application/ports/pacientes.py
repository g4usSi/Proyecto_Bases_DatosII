from typing import Protocol

from app.domain.paciente import Baja, NuevoPaciente, Paciente


class RepositorioPacientes(Protocol):
    """Pacientes de UNA institucion. El adaptador nunca recibe la institucion del cliente."""

    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        """Busca un paciente exclusivamente en la institucion del adaptador."""
        ...

    def buscar(self, palabras: tuple[str, ...], limite: int) -> list[Paciente]:
        """Pacientes cuyo nombre coincide con TODAS las palabras (regla en domain/busqueda.py).

        `palabras` ya viene en minusculas y sin acentos. Orden: apellidos, nombres,
        identificador. Incluye archivados (el resultado indica `archivado`). No hace
        falta devolver contacto ni alergias.
        """
        ...

    def registrar(self, datos: NuevoPaciente) -> Paciente:
        """Prepara el alta; se confirma cuando el caso de uso llama a commit()."""
        ...

    def archivar(self, id_paciente: str, baja: Baja) -> None:
        """Marca el historial como archivado sin borrar informacion clinica.

        Debe ser condicional en el motor (p. ej. UPDATE ... WHERE estado = 'Activo' o
        una transaccion de Firestore): si otra solicitud lo archivo primero, lanzar
        PacienteArchivado en vez de sobrescribir la baja anterior.
        """
        ...
