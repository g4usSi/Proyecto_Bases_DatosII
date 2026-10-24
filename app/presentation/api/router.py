from fastapi import APIRouter

from app.presentation.api.routes import auth, citas, odontograma, pacientes

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(pacientes.router)
api_router.include_router(odontograma.router)
api_router.include_router(citas.router)
