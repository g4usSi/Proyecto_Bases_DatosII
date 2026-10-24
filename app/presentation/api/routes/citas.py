from typing import Annotated

from fastapi import APIRouter, Path, Query, status
from pydantic import AwareDatetime

from app.application.use_cases.citas import AgendarCita, CambiarEstadoCita, ConsultarAgenda
from app.domain.cita import NuevaCita
from app.presentation.api.dependencies import ContextoGestionarCitas, ContextoLeerCitas
from app.presentation.api.schemas.cita import CambioEstadoCita, CitaCrear, CitaResponse

router = APIRouter(prefix="/citas", tags=["Citas"])


@router.post("", response_model=CitaResponse, status_code=status.HTTP_201_CREATED)
def agendar_cita(datos: CitaCrear, contexto: ContextoGestionarCitas) -> CitaResponse:
    """Reserva un horario. 409 si el profesional ya tiene una cita que se cruza."""
    cita = AgendarCita(contexto.unidad).ejecutar(
        contexto.usuario,
        NuevaCita(
            datos.id_paciente,
            datos.id_profesional,
            datos.inicio,
            datos.duracion_minutos,
            datos.motivo,
        ),
    )
    return CitaResponse.model_validate(cita)


@router.get("", response_model=list[CitaResponse])
def agenda(
    desde: Annotated[AwareDatetime, Query()],
    hasta: Annotated[AwareDatetime, Query()],
    contexto: ContextoLeerCitas,
    id_profesional: Annotated[str | None, Query(max_length=64)] = None,
) -> list[CitaResponse]:
    """Citas con inicio entre `desde` y `hasta` (maximo 31 dias)."""
    citas = ConsultarAgenda(contexto.unidad).ejecutar(desde, hasta, id_profesional)
    return [CitaResponse.model_validate(c) for c in citas]


@router.post("/{id_cita}/estado", response_model=CitaResponse)
def cambiar_estado(
    id_cita: Annotated[str, Path(min_length=1, max_length=128)],
    datos: CambioEstadoCita,
    contexto: ContextoGestionarCitas,
) -> CitaResponse:
    """programada -> atendida | cancelada (con motivo) | no_asistio."""
    cita = CambiarEstadoCita(contexto.unidad).ejecutar(
        contexto.usuario, id_cita, datos.estado, datos.motivo
    )
    return CitaResponse.model_validate(cita)
