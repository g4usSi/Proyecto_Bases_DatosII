from typing import Protocol

from app.domain.tutores import CambiosTutor, NuevoTutor, Tutor, TutorDePaciente, Vinculo


class RepositorioTutores(Protocol):
    """Tutores del Centro Pediatrico (los demas motores responden 501)."""

    def listar(self, id_paciente: str) -> list[TutorDePaciente]:
        """Primero el principal; luego por apellidos."""
        ...

    def buscar_por_documento(self, documento: str) -> Tutor | None: ...

    def listar_religiones(self) -> list[str]:
        """Nombres del catalogo de religiones, en orden alfabetico."""
        ...

    def vincular(
        self,
        id_paciente: str,
        vinculo: Vinculo,
        id_tutor: str | None = None,
        nuevo: NuevoTutor | None = None,
    ) -> TutorDePaciente:
        """Vincula un tutor existente (id_tutor) o crea uno (nuevo). Si es principal, el
        anterior deja de serlo. ConflictoEstado si ya estaba vinculado o el documento existe."""
        ...

    def cambiar(
        self, id_paciente: str, id_tutor: str, cambios: CambiosTutor
    ) -> TutorDePaciente: ...
