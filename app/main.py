import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap.container import Contenedor
from app.bootstrap.factory import crear_contenedor
from app.core.config import Settings
from app.presentation.api.handlers import registrar_manejadores
from app.presentation.api.router import api_router
from app.presentation.api.routes import health
from app.presentation.web import montar_frontend


def create_app(settings: Settings | None = None, contenedor: Contenedor | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")

    contenedor = contenedor if contenedor is not None else crear_contenedor(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            contenedor.cerrar()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="API comun de historiales clinicos. Base de arquitectura hexagonal.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.contenedor = contenedor

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    registrar_manejadores(app)
    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.api_prefix)
    montar_frontend(app)

    @app.get("/", tags=["Sistema"])
    def inicio() -> dict[str, str]:
        return {"nombre": settings.app_name, "version": settings.app_version, "docs": "/docs"}

    return app


app = create_app()
