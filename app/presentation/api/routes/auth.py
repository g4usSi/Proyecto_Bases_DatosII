from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from app.application.errores import IntegracionNoConfigurada
from app.application.use_cases.profesionales import CambiarContrasena
from app.bootstrap.container import Contenedor
from app.domain.errores import TokenInvalido
from app.domain.identidad import UsuarioAutenticado
from app.presentation.api.dependencies import obtener_contenedor, obtener_usuario_actual
from app.presentation.api.schemas.identidad import LoginRequest, LoginResponse, UsuarioResponse
from app.presentation.api.schemas.profesionales import CambiarContrasenaRequest

router = APIRouter(prefix="/auth", tags=["Autenticacion"])


@router.post("/login", response_model=LoginResponse)
def iniciar_sesion(
    datos: LoginRequest,
    response: Response,
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
) -> LoginResponse:
    if contenedor.inicio_sesion is None:
        raise IntegracionNoConfigurada("La identidad central todavia no esta configurada.")
    try:
        sesion = contenedor.inicio_sesion.iniciar_sesion(
            datos.correo, datos.password.get_secret_value()
        )
    except TokenInvalido as error:
        raise HTTPException(status_code=401, detail="Correo o contrasena invalidos.") from error
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(
        access_token=sesion.access_token,
        expires_in=sesion.expires_in,
        usuario=UsuarioResponse.de(sesion.usuario),
    )


@router.post("/logout", status_code=204)
def cerrar_sesion(
    usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
) -> Response:
    if contenedor.inicio_sesion is None:
        raise IntegracionNoConfigurada("La identidad central todavia no esta configurada.")
    contenedor.inicio_sesion.cerrar_sesion(usuario.id_usuario)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/me", response_model=UsuarioResponse)
def usuario_actual(
    usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
) -> UsuarioResponse:
    return UsuarioResponse.de(usuario)


@router.post("/cambiar-contrasena", response_model=LoginResponse)
def cambiar_contrasena(
    datos: CambiarContrasenaRequest,
    response: Response,
    usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
) -> LoginResponse:
    """Cambia TU contrasena. Cierra tus otras sesiones y devuelve un token nuevo.

    Una contrasena actual incorrecta responde 422 y cuenta como intento fallido de acceso.
    """
    if (
        contenedor.cuentas is None
        or contenedor.administracion is None
        or contenedor.cifrador is None
        or contenedor.inicio_sesion is None
    ):
        raise IntegracionNoConfigurada("La identidad central todavia no esta configurada.")
    sesion = CambiarContrasena(
        contenedor.cuentas, contenedor.administracion, contenedor.cifrador, contenedor.inicio_sesion
    ).ejecutar(
        usuario,
        datos.contrasena_actual.get_secret_value(),
        datos.contrasena_nueva.get_secret_value(),
    )
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(
        access_token=sesion.access_token,
        expires_in=sesion.expires_in,
        usuario=UsuarioResponse.de(sesion.usuario),
    )
