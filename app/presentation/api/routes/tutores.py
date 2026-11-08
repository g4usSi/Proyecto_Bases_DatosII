"""Tutores del paciente (Centro Pediatrico; otros establecimientos: 501)."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.application.use_cases.tutores import CambiarTutor, ConsultarTutores, VincularTutor
from app.domain.tutores import CambiosTutor, NuevoTutor, Vinculo
from app.presentation.api.dependencies import ContextoLeerPaciente, ContextoRegistrarPaciente
from app.presentation.api.schemas.tutores import (
    TutorCambios,
    TutorDePacienteResponse,
    TutorResponse,
    TutorVincular,
)

router = APIRouter(tags=["Pediatria"])

IdPaciente = Annotated[str, Path(min_length=1, max_length=128)]
IdTutor = Annotated[str, Path(min_length=1, max_length=20)]


@router.get("/pacientes/{id_paciente}/tutores", response_model=list[TutorDePacienteResponse])
def tutores_del_paciente(
    id_paciente: IdPaciente, contexto: ContextoLeerPaciente
) -> list[TutorDePacienteResponse]:
    """Primero el principal. `autorizado` indica quien puede recoger al paciente."""
    tutores = ConsultarTutores(contexto.unidad).del_paciente(id_paciente)
    return [TutorDePacienteResponse.model_validate(t) for t in tutores]


@router.get("/tutores", response_model=TutorResponse)
def buscar_tutor(
    contexto: ContextoLeerPaciente,
    documento: Annotated[str, Query(min_length=1, max_length=30)],
) -> TutorResponse:
    """Busca un tutor por DPI/pasaporte exacto (para vincularlo a un hermano). 404 si no hay."""
    return TutorResponse.model_validate(ConsultarTutores(contexto.unidad).por_documento(documento))


@router.get("/religiones", response_model=list[str])
def religiones(contexto: ContextoRegistrarPaciente) -> list[str]:
    """Religiones ya registradas, para sugerirlas al escribir la del tutor."""
    return ConsultarTutores(contexto.unidad).religiones()


@router.post(
    "/pacientes/{id_paciente}/tutores",
    response_model=TutorDePacienteResponse,
    status_code=status.HTTP_201_CREATED,
)
def vincular_tutor(
    id_paciente: IdPaciente, datos: TutorVincular, contexto: ContextoRegistrarPaciente
) -> TutorDePacienteResponse:
    """Vincula un tutor existente o uno nuevo. Si es principal, el anterior deja de serlo.
    409 si ya estaba vinculado o si el documento ya existe; 409 si el historial esta archivado."""
    nuevo = None
    if datos.tutor is not None:
        t = datos.tutor
        nuevo = NuevoTutor(
            t.nombres, t.apellidos, t.documento, t.telefono, t.correo, t.direccion, t.religion
        )
    resultado = VincularTutor(contexto.unidad).ejecutar(
        id_paciente,
        Vinculo(datos.parentesco, datos.es_principal, datos.autorizado),
        datos.id_tutor,
        nuevo,
    )
    return TutorDePacienteResponse.model_validate(resultado)


@router.patch("/pacientes/{id_paciente}/tutores/{id_tutor}", response_model=TutorDePacienteResponse)
def cambiar_tutor(
    id_paciente: IdPaciente,
    id_tutor: IdTutor,
    datos: TutorCambios,
    contexto: ContextoRegistrarPaciente,
) -> TutorDePacienteResponse:
    """Parentesco, principal, autorizacion, contacto o religion (estos dos son del tutor).
    Un texto vacio borra el dato."""
    cambios = CambiosTutor(
        datos.parentesco,
        datos.es_principal,
        datos.autorizado,
        datos.telefono,
        datos.correo,
        datos.direccion,
        datos.religion,
    )
    return TutorDePacienteResponse.model_validate(
        CambiarTutor(contexto.unidad).ejecutar(id_paciente, id_tutor, cambios)
    )
