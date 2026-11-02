from decimal import Decimal
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from app.application.use_cases.plataforma import ResumenDePlataforma
from app.bootstrap.container import Contenedor
from app.presentation.api.dependencies import SuperusuarioDePlataforma, obtener_contenedor

router = APIRouter(tags=["Plataforma"])


class ResumenEntidadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    administrador_activo: str | None
    personal_activo: int
    personal_sin_acceso: int
    pacientes_registrados: int
    citas_hoy: int
    camas_ocupadas: int | None = None
    emergencias_abiertas: int | None = None
    cobros_abiertos: int | None = None
    saldo_pendiente: Decimal | None = None
    ordenes_abiertas: int | None = None


@router.get("/plataforma/resumen", response_model=dict[str, ResumenEntidadResponse | None])
def resumen_plataforma(
    request: Request,
    usuario: SuperusuarioDePlataforma,
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
):
    return ResumenDePlataforma(
        contenedor.administracion,
        contenedor.crear_unidad_trabajo,
        ZoneInfo(request.app.state.settings.zona_horaria),
    ).ejecutar()
