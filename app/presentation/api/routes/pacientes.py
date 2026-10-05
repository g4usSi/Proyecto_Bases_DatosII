from typing import Annotated

from fastapi import APIRouter, Depends, Path

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.application.use_cases.consultar_paciente import ConsultarPaciente
from app.presentation.api.dependencies import obtener_unidad_trabajo
from app.presentation.api.schemas.paciente import PacienteResponse

router = APIRouter(prefix="/pacientes", tags=["Pacientes"])


@router.get("/{id_paciente}", response_model=PacienteResponse)
def consultar_paciente(
    id_paciente: Annotated[str, Path(min_length=1, max_length=128)],
    unidad: Annotated[UnidadDeTrabajo, Depends(obtener_unidad_trabajo)],
) -> PacienteResponse:
    paciente = ConsultarPaciente(unidad).ejecutar(id_paciente)
    return PacienteResponse.model_validate(paciente)
