from fastapi import APIRouter

from app.presentation.api.routes import (
    auth,
    citas,
    cobros,
    hospital,
    laboratorio,
    odontograma,
    pacientes,
    pediatria,
    plataforma,
    profesionales,
    tutores,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(profesionales.router)
api_router.include_router(pacientes.router)
api_router.include_router(odontograma.router)
api_router.include_router(citas.router)
api_router.include_router(pediatria.router)
api_router.include_router(laboratorio.router)
api_router.include_router(hospital.router)
api_router.include_router(cobros.router)
api_router.include_router(tutores.router)
api_router.include_router(plataforma.router)
