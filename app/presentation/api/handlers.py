from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.application.errores import IntegracionNoConfigurada
from app.domain.errores import AccesoDenegado, PacienteNoEncontrado, TokenInvalido


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
    async def paciente_no_encontrado(request: Request, error: PacienteNoEncontrado) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(error)})

    @app.exception_handler(AccesoDenegado)
    async def acceso_denegado(request: Request, error: AccesoDenegado) -> JSONResponse:
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
