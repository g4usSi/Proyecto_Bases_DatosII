from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.application.use_cases.pediatria import (
    AplicarDosis,
    CancelarDosis,
    ConsultarCatalogoVacunas,
    ConsultarCrecimiento,
    ConsultarEsquema,
    GenerarEsquemaRecomendado,
    ProgramarDosis,
    RegistrarControlCrecimiento,
)
from app.domain.pediatria import NuevoControl
from app.presentation.api.dependencies import ContextoLeerHistorial, ContextoRegistrarConsulta
from app.presentation.api.schemas.pediatria import (
    ControlCrear,
    ControlResponse,
    DosisAplicar,
    DosisProgramar,
    DosisResponse,
    TipoVacunaResponse,
)

router = APIRouter(tags=["Pediatria"])

IdPaciente = Annotated[str, Path(min_length=1, max_length=128)]
IdDosis = Annotated[str, Path(min_length=1, max_length=20, pattern=r"^\d+$")]


@router.post(
    "/pacientes/{id_paciente}/crecimiento",
    response_model=ControlResponse,
    status_code=status.HTTP_201_CREATED,
)
def registrar_control(
    id_paciente: IdPaciente, datos: ControlCrear, contexto: ContextoRegistrarConsulta
) -> ControlResponse:
    """Agrega un control de crecimiento (no se edita despues). Solo Centro Pediatrico."""
    control = RegistrarControlCrecimiento(contexto.unidad).ejecutar(
        id_paciente, NuevoControl(**datos.model_dump())
    )
    return ControlResponse.model_validate(control)


@router.get("/pacientes/{id_paciente}/crecimiento", response_model=list[ControlResponse])
def historial_crecimiento(
    id_paciente: IdPaciente,
    contexto: ContextoLeerHistorial,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ControlResponse]:
    controles = ConsultarCrecimiento(contexto.unidad).ejecutar(id_paciente, limite)
    return [ControlResponse.model_validate(c) for c in controles]


@router.get("/vacunas", response_model=list[TipoVacunaResponse])
def catalogo_de_vacunas(contexto: ContextoLeerHistorial) -> list[TipoVacunaResponse]:
    tipos = ConsultarCatalogoVacunas(contexto.unidad).tipos()
    return [TipoVacunaResponse.model_validate(t) for t in tipos]


@router.get("/pacientes/{id_paciente}/vacunacion", response_model=list[DosisResponse])
def esquema_de_vacunacion(
    id_paciente: IdPaciente, contexto: ContextoLeerHistorial
) -> list[DosisResponse]:
    dosis = ConsultarEsquema(contexto.unidad).ejecutar(id_paciente)
    return [DosisResponse.model_validate(d) for d in dosis]


@router.post(
    "/pacientes/{id_paciente}/vacunacion",
    response_model=DosisResponse,
    status_code=status.HTTP_201_CREATED,
)
def programar_dosis(
    id_paciente: IdPaciente, datos: DosisProgramar, contexto: ContextoRegistrarConsulta
) -> DosisResponse:
    dosis = ProgramarDosis(contexto.unidad).ejecutar(
        id_paciente, datos.id_vacuna, datos.numero_dosis, datos.fecha_programada
    )
    return DosisResponse.model_validate(dosis)


@router.post(
    "/pacientes/{id_paciente}/vacunacion/esquema-recomendado",
    response_model=list[DosisResponse],
    status_code=status.HTTP_201_CREATED,
)
def generar_esquema_recomendado(
    id_paciente: IdPaciente, contexto: ContextoRegistrarConsulta
) -> list[DosisResponse]:
    """Programa las vacunas del catalogo segun su edad recomendada (no duplica)."""
    dosis = GenerarEsquemaRecomendado(contexto.unidad).ejecutar(id_paciente)
    return [DosisResponse.model_validate(d) for d in dosis]


@router.post("/pacientes/{id_paciente}/vacunacion/{id_dosis}/aplicar", response_model=DosisResponse)
def aplicar_dosis(
    id_paciente: IdPaciente,
    id_dosis: IdDosis,
    datos: DosisAplicar,
    contexto: ContextoRegistrarConsulta,
) -> DosisResponse:
    """Marca la dosis como aplicada; el aplicador es quien tiene la sesion. Sin stock ni lotes."""
    dosis = AplicarDosis(contexto.unidad).ejecutar(
        contexto.usuario, id_paciente, id_dosis, datos.observaciones_reaccion
    )
    return DosisResponse.model_validate(dosis)


@router.post(
    "/pacientes/{id_paciente}/vacunacion/{id_dosis}/cancelar", response_model=DosisResponse
)
def cancelar_dosis(
    id_paciente: IdPaciente, id_dosis: IdDosis, contexto: ContextoRegistrarConsulta
) -> DosisResponse:
    dosis = CancelarDosis(contexto.unidad).ejecutar(id_paciente, id_dosis)
    return DosisResponse.model_validate(dosis)
