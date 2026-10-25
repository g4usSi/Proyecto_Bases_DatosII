import logging
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel

from app.domain.institucion import Institucion

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sistema"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyResponse(BaseModel):
    status: Literal["ok", "degradado"]
    instituciones: dict[str, Literal["ok", "no_disponible", "no_configurada"]]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Confirma que la API responde; no comprueba conexiones a bases de datos."""
    return HealthResponse()


@router.get("/health/ready", response_model=ReadyResponse)
def ready(request: Request, response: Response) -> ReadyResponse:
    """Comprueba cada base configurada con un ping. 503 si alguna configurada no responde.

    Una institucion sin configurar no cuenta como falla (un companero puede trabajar con
    menos motores). No revela detalles del error: van al log del servidor.
    """
    contenedor = request.app.state.contenedor
    estados: dict[str, Literal["ok", "no_disponible", "no_configurada"]] = {}
    for institucion in Institucion:
        verificar = contenedor.verificaciones.get(institucion)
        if verificar is None:
            estados[institucion.value] = "no_configurada"
            continue
        try:
            verificar()
            estados[institucion.value] = "ok"
        except Exception as error:  # noqa: BLE001 - cualquier falla del motor significa "no disponible"
            logger.warning("Verificacion de %s fallo: %s", institucion.value, error)
            estados[institucion.value] = "no_disponible"
    degradado = "no_disponible" in estados.values()
    if degradado:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="degradado" if degradado else "ok", instituciones=estados)
