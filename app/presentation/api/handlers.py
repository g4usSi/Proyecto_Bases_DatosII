from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.application.errores import IntegracionNoConfigurada, OperacionPendiente
from app.domain.errores import (
    AccesoDenegado,
    CitaNoEncontrada,
    ConflictoAgenda,
    ConflictoEstado,
    ConsultaNoEncontrada,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
    RegistroNoEncontrado,
    TokenInvalido,
)


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def entrada_invalida(request: Request, error: RequestValidationError) -> JSONResponse:
        # FastAPI normalmente devuelve "input"; podria reflejar una contrasena enviada.
        detalles = [
            {clave: detalle[clave] for clave in ("loc", "msg", "type")}
            for detalle in error.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": detalles})

    @app.exception_handler(PacienteNoEncontrado)
    @app.exception_handler(CitaNoEncontrada)
    @app.exception_handler(ConsultaNoEncontrada)
    @app.exception_handler(RegistroNoEncontrado)
    async def no_encontrado(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(error)})

    @app.exception_handler(AccesoDenegado)
    @app.exception_handler(ProfesionalNoVinculado)
    async def acceso_denegado(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(error)})

    @app.exception_handler(TokenInvalido)
    async def token_invalido(request: Request, error: TokenInvalido) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "La sesion no es valida o ha expirado."},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(IntegracionNoConfigurada)
    async def integracion_no_configurada(
        request: Request, error: IntegracionNoConfigurada
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(error)}
        )

    @app.exception_handler(PacienteArchivado)
    @app.exception_handler(ConflictoAgenda)
    @app.exception_handler(ConflictoEstado)
    async def conflicto(request: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(error)})

    @app.exception_handler(OperacionPendiente)
    async def operacion_pendiente(request: Request, error: OperacionPendiente) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, content={"detail": str(error)}
        )

    @app.exception_handler(DatosInvalidos)
    async def datos_invalidos(request: Request, error: DatosInvalidos) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": str(error)}
        )
