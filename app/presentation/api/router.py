from fastapi import APIRouter

from app.presentation.api.routes import auth, pacientes

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(pacientes.router)
