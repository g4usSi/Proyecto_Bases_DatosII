from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.errores import IntegracionNoConfigurada
from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.bootstrap.container import Contenedor
from app.domain import permisos
from app.domain.identidad import UsuarioAutenticado

bearer = HTTPBearer(auto_error=False)


def obtener_contenedor(request: Request) -> Contenedor:
    return request.app.state.contenedor


def obtener_usuario_actual(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
) -> UsuarioAutenticado:
    if credenciales is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Debes iniciar sesion.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if contenedor.autenticador is None:
        raise IntegracionNoConfigurada("La autenticacion todavia no esta configurada.")
    return contenedor.autenticador.verificar_token(credenciales.credentials)


def exigir_lectura_pacientes(
    usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
) -> UsuarioAutenticado:
    usuario.exigir_permiso("pacientes:leer")
    return usuario


def obtener_unidad_trabajo(
    usuario: Annotated[UsuarioAutenticado, Depends(exigir_lectura_pacientes)],
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
) -> UnidadDeTrabajo:
    # La institucion siempre proviene del autenticador, nunca de un parametro del cliente.
    return contenedor.crear_unidad_trabajo(usuario.institucion)


@dataclass(frozen=True, slots=True)
class Contexto:
    """Usuario verificado + unidad de trabajo del motor de SU institucion."""

    usuario: UsuarioAutenticado
    unidad: UnidadDeTrabajo


def contexto_con_permiso(permiso: str) -> Callable[..., Contexto]:
    """Dependencia que exige un permiso y abre el motor de la institucion del token."""

    def dependencia(
        usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
        contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
    ) -> Contexto:
        usuario.exigir_permiso(permiso)
        return Contexto(usuario, contenedor.crear_unidad_trabajo(usuario.institucion))

    return dependencia


# Permisos de identidad.permiso (database/postgresql/002 y 006).
_con = contexto_con_permiso
ContextoLeerPaciente = Annotated[Contexto, Depends(_con(permisos.PACIENTES_LEER))]
ContextoRegistrarPaciente = Annotated[Contexto, Depends(_con(permisos.PACIENTES_REGISTRAR))]
ContextoLeerHistorial = Annotated[Contexto, Depends(_con(permisos.HISTORIALES_LEER))]
ContextoRegistrarConsulta = Annotated[Contexto, Depends(_con(permisos.CONSULTAS_REGISTRAR))]
ContextoArchivar = Annotated[Contexto, Depends(_con(permisos.HISTORIALES_ARCHIVAR))]
ContextoLeerCitas = Annotated[Contexto, Depends(_con(permisos.CITAS_LEER))]
ContextoGestionarCitas = Annotated[Contexto, Depends(_con(permisos.CITAS_GESTIONAR))]
