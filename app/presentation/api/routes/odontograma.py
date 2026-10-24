from typing import Annotated

from fastapi import APIRouter, Path

from app.application.use_cases.odontograma import ActualizarPieza, ConsultarOdontograma
from app.presentation.api.dependencies import ContextoLeerHistorial, ContextoRegistrarConsulta
from app.presentation.api.schemas.odontograma import (
    OdontogramaResponse,
    PiezaActualizar,
    PiezaResponse,
)

router = APIRouter(prefix="/pacientes", tags=["Odontograma"])

IdPaciente = Annotated[str, Path(min_length=1, max_length=128)]


@router.get("/{id_paciente}/odontograma", response_model=OdontogramaResponse)
def consultar_odontograma(
    id_paciente: IdPaciente, contexto: ContextoLeerHistorial
) -> OdontogramaResponse:
    odontograma = ConsultarOdontograma(contexto.unidad).ejecutar(id_paciente)
    return OdontogramaResponse(
        id_paciente=odontograma.id_paciente,
        piezas=[PiezaResponse.model_validate(p) for p in odontograma.piezas.values()],
    )


@router.put("/{id_paciente}/odontograma/piezas/{pieza}", response_model=PiezaResponse)
def actualizar_pieza(
    id_paciente: IdPaciente,
    pieza: Annotated[str, Path(pattern=r"^[1-8][1-8]$", description="Numeracion FDI, p. ej. 36")],
    datos: PiezaActualizar,
    contexto: ContextoRegistrarConsulta,
) -> PiezaResponse:
    estado = ActualizarPieza(contexto.unidad).ejecutar(
        contexto.usuario,
        id_paciente,
        pieza,
        datos.estado,
        tuple(datos.superficies),
        datos.nota,
    )
    return PiezaResponse.model_validate(estado)
