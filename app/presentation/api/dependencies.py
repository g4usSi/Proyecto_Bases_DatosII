from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.errores import IntegracionNoConfigurada
from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.bootstrap.container import Contenedor
from app.core import auditoria
from app.domain import permisos
from app.domain.errores import AccesoDenegado, DatosInvalidos
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion

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
    if usuario.es_plataforma:
        raise AccesoDenegado("Una cuenta de plataforma no accede a datos clinicos.")
    return contenedor.crear_unidad_trabajo(usuario.institucion)


@dataclass(frozen=True, slots=True)
class Contexto:
    """Usuario verificado + unidad de trabajo del motor de SU institucion."""

    usuario: UsuarioAutenticado
    unidad: UnidadDeTrabajo


def _auditar(request: Request, usuario: UsuarioAutenticado, permiso: str, permitido: bool) -> None:
    ruta = request.scope.get("route")
    plantilla = getattr(ruta, "path", request.url.path)  # sin ids reales: /pacientes/{id_paciente}
    paciente = request.path_params.get("id_paciente")
    registrar = auditoria.acceso if permitido else auditoria.denegado
    registrar(usuario, request.method, plantilla, permiso, paciente)


def usuario_con_permiso(permiso: str) -> Callable[..., UsuarioAutenticado]:
    """Exige el permiso SIN abrir el motor clinico (la identidad vive en PostgreSQL)."""

    def dependencia(
        request: Request,
        usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
    ) -> UsuarioAutenticado:
        if permiso not in usuario.permisos or (
            permiso == permisos.PLATAFORMA_ADMINISTRAR and not usuario.es_plataforma
        ):
            _auditar(request, usuario, permiso, permitido=False)
            raise AccesoDenegado("No tienes permiso para realizar esta operacion.")
        _auditar(request, usuario, permiso, permitido=True)
        return usuario

    return dependencia


def contexto_con_permiso(permiso: str) -> Callable[..., Contexto]:
    """Dependencia que exige un permiso y abre el motor de la institucion del token."""

    return contexto_con_alguno(permiso)


def contexto_con_alguno(*permisos_validos: str) -> Callable[..., Contexto]:
    """Exige UNO de los permisos y abre el motor de la institucion del token.

    Cada decision (permitida o denegada) queda en la bitacora de auditoria.
    """

    def dependencia(
        request: Request,
        usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
        contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
    ) -> Contexto:
        elegido = next((p for p in permisos_validos if p in usuario.permisos), None)
        if elegido is None or usuario.es_plataforma:
            _auditar(request, usuario, permisos_validos[0], permitido=False)
            raise AccesoDenegado("No tienes permiso para realizar esta operacion.")
        _auditar(request, usuario, elegido, permitido=True)
        return Contexto(usuario, contenedor.crear_unidad_trabajo(usuario.institucion))

    return dependencia


def contexto_con_todos(*exigidos: str) -> Callable[..., Contexto]:
    """Exige TODOS los permisos y abre el motor de la institucion del token."""

    def dependencia(
        request: Request,
        usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
        contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
    ) -> Contexto:
        for permiso in exigidos:
            if permiso not in usuario.permisos:
                _auditar(request, usuario, permiso, permitido=False)
                raise AccesoDenegado("No tienes permiso para realizar esta operacion.")
        _auditar(request, usuario, exigidos[0], permitido=True)
        return Contexto(usuario, contenedor.crear_unidad_trabajo(usuario.institucion))

    return dependencia


def gestor_de_profesionales(
    usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
) -> UsuarioAutenticado:
    if permisos.PROFESIONALES_ADMINISTRAR in usuario.permisos and not usuario.es_plataforma:
        return usuario
    if permisos.PLATAFORMA_ADMINISTRAR in usuario.permisos and usuario.es_plataforma:
        return usuario
    raise AccesoDenegado("No tienes permiso para administrar cuentas.")


def contexto_pagos_lectura(
    request: Request,
    usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
    establecimiento: Annotated[Institucion | None, Query()] = None,
) -> Contexto:
    usuario.exigir_permiso(permisos.PAGOS_VER)
    institucion = usuario.institucion
    if usuario.es_plataforma:
        usuario.exigir_permiso(permisos.PLATAFORMA_ADMINISTRAR)
        if establecimiento not in {Institucion.HOSPITAL_GENERAL, Institucion.CENTRO_PEDIATRICO}:
            raise DatosInvalidos("Selecciona hospital_general o centro_pediatrico.")
        institucion = establecimiento
    elif establecimiento is not None and establecimiento != institucion:
        raise AccesoDenegado("Solo puedes consultar los cobros de tu institucion.")
    _auditar(request, usuario, permisos.PAGOS_VER, permitido=True)
    return Contexto(usuario, contenedor.crear_unidad_trabajo(institucion))


def contexto_departamentos(
    request: Request,
    usuario: Annotated[UsuarioAutenticado, Depends(obtener_usuario_actual)],
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
    establecimiento: Annotated[Institucion | None, Query()] = None,
) -> Contexto:
    """Areas del Hospital: el superusuario las pide para asignar personal; no son datos clinicos."""
    if usuario.es_plataforma:
        usuario.exigir_permiso(permisos.PLATAFORMA_ADMINISTRAR)
        if establecimiento != Institucion.HOSPITAL_GENERAL:
            raise DatosInvalidos("Selecciona hospital_general.")
        _auditar(request, usuario, permisos.PLATAFORMA_ADMINISTRAR, permitido=True)
        return Contexto(usuario, contenedor.crear_unidad_trabajo(establecimiento))
    if establecimiento is not None and establecimiento != usuario.institucion:
        raise AccesoDenegado("Solo puedes consultar las areas de tu institucion.")
    return contexto_con_alguno(permisos.PACIENTES_LEER, permisos.PROFESIONALES_ADMINISTRAR)(
        request, usuario, contenedor
    )


# Permisos de identidad.permiso (database/postgresql/002, 006 y 011).
_con = contexto_con_permiso
ContextoLeerPaciente = Annotated[Contexto, Depends(_con(permisos.PACIENTES_LEER))]
ContextoRegistrarPaciente = Annotated[Contexto, Depends(_con(permisos.PACIENTES_REGISTRAR))]
# Agregar compara con las ya registradas: un rechazo por duplicado revela que el paciente
# tiene esa alergia, asi que tambien exige poder leerlas (la secretaria no puede).
ContextoAgregarAlergias = Annotated[
    Contexto,
    Depends(contexto_con_todos(permisos.PACIENTES_REGISTRAR, permisos.HISTORIALES_LEER)),
]
ContextoLeerHistorial = Annotated[Contexto, Depends(_con(permisos.HISTORIALES_LEER))]
ContextoRegistrarConsulta = Annotated[Contexto, Depends(_con(permisos.CONSULTAS_REGISTRAR))]
ContextoArchivar = Annotated[Contexto, Depends(_con(permisos.HISTORIALES_ARCHIVAR))]
ContextoLeerCitas = Annotated[Contexto, Depends(_con(permisos.CITAS_LEER))]
ContextoGestionarCitas = Annotated[Contexto, Depends(_con(permisos.CITAS_GESTIONAR))]
ContextoResultadosLab = Annotated[Contexto, Depends(_con(permisos.LABORATORIO_RESULTADOS))]
ContextoValidarLab = Annotated[Contexto, Depends(_con(permisos.LABORATORIO_VALIDAR))]
AdministradorDeProfesionales = Annotated[UsuarioAutenticado, Depends(gestor_de_profesionales)]
SuperusuarioDePlataforma = Annotated[
    UsuarioAutenticado, Depends(usuario_con_permiso(permisos.PLATAFORMA_ADMINISTRAR))
]
UsuarioLeerCitas = Annotated[UsuarioAutenticado, Depends(usuario_con_permiso(permisos.CITAS_LEER))]
ContextoDepartamentos = Annotated[Contexto, Depends(contexto_departamentos)]
ContextoVerPagos = Annotated[Contexto, Depends(contexto_pagos_lectura)]
ContextoRegistrarPagos = Annotated[Contexto, Depends(_con(permisos.PAGOS_REGISTRAR))]
ContextoGestionarCamas = Annotated[Contexto, Depends(_con(permisos.CAMAS_GESTIONAR))]
# El catalogo de vacunas no es un dato clinico: lo lee tambien el administrador, que lo mantiene.
ContextoLeerCatalogo = Annotated[
    Contexto,
    Depends(contexto_con_alguno(permisos.HISTORIALES_LEER, permisos.PROFESIONALES_ADMINISTRAR)),
]
ContextoAdministrarCatalogo = Annotated[Contexto, Depends(_con(permisos.PROFESIONALES_ADMINISTRAR))]
ContextoLeerLab = Annotated[
    Contexto,
    Depends(contexto_con_alguno(permisos.HISTORIALES_LEER, permisos.LABORATORIO_RESULTADOS)),
]
