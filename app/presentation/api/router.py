from fastapi import APIRouter

from app.presentation.api.routes import (
    auth,
    citas,
    hospital,
    laboratorio,
    odontograma,
    pacientes,
    pediatria,
    profesionales,
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
