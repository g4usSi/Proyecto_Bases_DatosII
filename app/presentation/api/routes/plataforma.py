"""Administracion general (superusuario de plataforma): resumen de las cuatro entidades.

Solo conteos: ningun nombre, id ni dato de pacientes. Exige plataforma:administrar.
"""

from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from app.application.errores import IntegracionNoConfigurada
from app.application.use_cases.plataforma import ResumenDePlataforma
from app.bootstrap.container import Contenedor
from app.presentation.api.dependencies import SuperusuarioDePlataforma, obtener_contenedor
from app.presentation.api.schemas.plataforma import ResumenPlataformaResponse

router = APIRouter(prefix="/plataforma", tags=["Plataforma"])


@router.get("/resumen", response_model=ResumenPlataformaResponse)
def resumen_de_plataforma(
    request: Request,
    superusuario: SuperusuarioDePlataforma,
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
) -> ResumenPlataformaResponse:
    """Por entidad: administrador activo, personal activo y sin acceso, pacientes registrados,
    citas de hoy y de la semana; camas ocupadas y emergencias (hospital), cobros y saldo por
    cobrar (hospital y pediatrico) y ordenes abiertas (laboratorio). Si un motor no responde,
    su entidad trae `indicadores: null` y la respuesta sigue siendo valida."""
    if contenedor.administracion is None:
        raise IntegracionNoConfigurada("La identidad central todavia no esta configurada.")
    zona = ZoneInfo(request.app.state.settings.zona_horaria)
    resumen = ResumenDePlataforma(
        contenedor.administracion, contenedor.crear_unidad_trabajo, zona
    ).ejecutar()
    return ResumenPlataformaResponse.de(resumen)
