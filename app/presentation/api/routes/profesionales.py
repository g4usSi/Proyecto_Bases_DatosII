"""Administracion del personal en dos niveles.

- Administrador de una entidad: su institucion sale del token; no ve ni gestiona cuentas
  de administracion y no elimina.
- Superusuario de plataforma: elige la entidad (`establecimiento`), crea administradores y
  es el unico que elimina (baja definitiva logica). Nunca se ve ni se gestiona a si mismo.

Las respuestas que muestran una contrasena generada llevan Cache-Control: no-store y no se
repiten.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.application.errores import IntegracionNoConfigurada
from app.application.use_cases.hospital import ConsultarDepartamentos
from app.application.use_cases.profesionales import AdministrarProfesionales
from app.bootstrap.container import Contenedor
from app.domain.administracion import (
    AccionBitacora,
    CambiosProfesional,
    EstadoCuenta,
    FiltroBitacora,
    NuevoProfesional,
)
from app.domain.institucion import Institucion
from app.presentation.api.dependencies import (
    ContextoDepartamentos,
    GestorDeProfesionales,
    UsuarioLeerCitas,
    obtener_contenedor,
)
from app.presentation.api.schemas.profesionales import (
    ContrasenaRestablecidaResponse,
    DepartamentoResponse,
    EntradaBitacoraResponse,
    ProfesionalAgendaResponse,
    ProfesionalCambiadoResponse,
    ProfesionalCambios,
    ProfesionalCreadoResponse,
    ProfesionalCrear,
    ProfesionalResponse,
    ResumenPersonalResponse,
)

router = APIRouter(tags=["Profesionales"])

IdProfesional = Annotated[str, Path(min_length=1, max_length=64)]
SIN_CACHE = {"Cache-Control": "no-store"}


Establecimiento = Annotated[
    Institucion | None,
    Query(description="Solo la administracion general: filtra por entidad."),
]


def caso_de_uso(
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
    gestor: GestorDeProfesionales,
) -> AdministrarProfesionales:
    if contenedor.administracion is None or contenedor.cifrador is None:
        raise IntegracionNoConfigurada("La identidad central todavia no esta configurada.")
    # El perfil local se crea en el motor de la institucion de la CUENTA (para el
    # superusuario puede ser cualquiera de las cuatro).
    return AdministrarProfesionales(
        contenedor.administracion, contenedor.cifrador, contenedor.crear_unidad_trabajo
    )


CasoDeUso = Annotated[AdministrarProfesionales, Depends(caso_de_uso)]


@router.post(
    "/profesionales",
    response_model=ProfesionalCreadoResponse,
    status_code=status.HTTP_201_CREATED,
)
def crear_profesional(
    datos: ProfesionalCrear,
    response: Response,
    gestor: GestorDeProfesionales,
    casos: CasoDeUso,
) -> ProfesionalCreadoResponse:
    """Alta de una cuenta. Administrador: en su institucion (sin `establecimiento`; rol
    administrador → 403). Superusuario: `establecimiento` obligatorio; puede crear al
    administrador de una entidad (409 si ya tiene uno activo). 409 si el correo ya existe."""
    resultado = casos.crear(
        gestor,
        NuevoProfesional(
            datos.correo,
            datos.nombres,
            datos.apellidos,
            datos.rol,
            frozenset(datos.permisos) if datos.permisos is not None else None,
            datos.id_departamento,
        ),
        datos.contrasena_inicial.get_secret_value() if datos.contrasena_inicial else None,
        datos.establecimiento,
    )
    response.headers.update(SIN_CACHE)
    return ProfesionalCreadoResponse(
        profesional=ProfesionalResponse.model_validate(resultado.ficha),
        vinculado=resultado.vinculado,
        contrasena_temporal=resultado.contrasena_temporal,
    )


@router.get("/profesionales", response_model=list[ProfesionalResponse])
def listar_profesionales(
    gestor: GestorDeProfesionales,
    casos: CasoDeUso,
    establecimiento: Establecimiento = None,
    rol: Annotated[str | None, Query(max_length=40)] = None,
    id_departamento: Annotated[int | None, Query(ge=1)] = None,
    estado: EstadoCuenta | None = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[ProfesionalResponse]:
    """Administrador: personal de su institucion, sin cuentas de administracion (pedir otra
    entidad es 403). Superusuario: todas las entidades o la pedida, con sus administradores.
    Nadie ve las cuentas eliminadas."""
    fichas = casos.listar(gestor, rol, id_departamento, estado, limite, establecimiento)
    return [ProfesionalResponse.model_validate(f) for f in fichas]


@router.get("/profesionales/resumen", response_model=ResumenPersonalResponse)
def resumen_del_personal(
    gestor: GestorDeProfesionales, casos: CasoDeUso, establecimiento: Establecimiento = None
) -> ResumenPersonalResponse:
    """Cuentas que requieren atencion, personal activo por rol (y por area en el hospital) y
    ultimos movimientos. Solo identidad central: no toca motores clinicos. El superusuario
    elige la entidad con `establecimiento` (obligatorio para el)."""
    return ResumenPersonalResponse.de(casos.resumen(gestor, establecimiento))


@router.get("/profesionales/bitacora", response_model=list[EntradaBitacoraResponse])
def bitacora_de_administracion(
    gestor: GestorDeProfesionales,
    casos: CasoDeUso,
    establecimiento: Establecimiento = None,
    accion: Annotated[list[AccionBitacora] | None, Query(description="Repetible")] = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    antes_de: Annotated[
        int | None, Query(ge=1, description="Cursor: id_evento de la ultima fila recibida")
    ] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[EntradaBitacoraResponse]:
    """Movimientos de administracion, del mas reciente al mas antiguo. Administrador: solo
    su entidad (pedir otra es 403). Superusuario: todas o la pedida. Nunca trae contrasenas."""
    filtro = FiltroBitacora(frozenset(accion) if accion else None, desde, hasta, antes_de, limite)
    entradas = casos.bitacora(gestor, filtro, establecimiento)
    return [EntradaBitacoraResponse.model_validate(e) for e in entradas]


@router.get("/profesionales/{id_profesional}", response_model=ProfesionalResponse)
def consultar_profesional(
    id_profesional: IdProfesional, gestor: GestorDeProfesionales, casos: CasoDeUso
) -> ProfesionalResponse:
    return ProfesionalResponse.model_validate(casos.obtener(gestor, id_profesional))


@router.patch("/profesionales/{id_profesional}", response_model=ProfesionalCambiadoResponse)
def cambiar_profesional(
    id_profesional: IdProfesional,
    datos: ProfesionalCambios,
    gestor: GestorDeProfesionales,
    casos: CasoDeUso,
) -> ProfesionalCambiadoResponse:
    """Area, permisos (lista completa), estado o nombre. Bloquear/desactivar corta el acceso
    de inmediato: sus sesiones abiertas dejan de valer. `estado: eliminada` es 422 (se usa
    DELETE) y una cuenta eliminada responde 409."""
    enviados = datos.model_fields_set
    cambios = CambiosProfesional(
        nombres=datos.nombres,
        apellidos=datos.apellidos,
        permisos=frozenset(datos.permisos) if datos.permisos is not None else None,
        estado=datos.estado,
        id_departamento=datos.id_departamento,
        quitar_departamento="id_departamento" in enviados and datos.id_departamento is None,
    )
    resultado = casos.actualizar(gestor, id_profesional, cambios)
    return ProfesionalCambiadoResponse(
        profesional=ProfesionalResponse.model_validate(resultado.ficha),
        vinculado=resultado.vinculado,
    )


@router.delete("/profesionales/{id_profesional}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_profesional(
    id_profesional: IdProfesional, gestor: GestorDeProfesionales, casos: CasoDeUso
) -> Response:
    """Baja definitiva logica (solo el superusuario; el administrador recibe 403). La cuenta
    no vuelve a iniciar sesion ni a habilitarse, sale de los listados, conserva su historial
    y su correo sigue reservado. 409 si ya estaba eliminada; 404 si es la propia cuenta."""
    casos.eliminar(gestor, id_profesional)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/profesionales/{id_profesional}/restablecer-contrasena",
    response_model=ContrasenaRestablecidaResponse,
)
def restablecer_contrasena(
    id_profesional: IdProfesional,
    response: Response,
    gestor: GestorDeProfesionales,
    casos: CasoDeUso,
) -> ContrasenaRestablecidaResponse:
    """Genera una contrasena nueva. El servidor la muestra UNA sola vez."""
    nueva = casos.restablecer_contrasena(gestor, id_profesional)
    response.headers.update(SIN_CACHE)
    return ContrasenaRestablecidaResponse(contrasena_temporal=nueva)


@router.get("/departamentos", response_model=list[DepartamentoResponse], tags=["Hospital"])
def listar_departamentos(contexto: ContextoDepartamentos) -> list[DepartamentoResponse]:
    """Areas del Hospital General (selector de area). Otras instituciones: 501."""
    departamentos = ConsultarDepartamentos(contexto.unidad).ejecutar()
    return [DepartamentoResponse.model_validate(d) for d in departamentos]


@router.get("/citas/profesionales", response_model=list[ProfesionalAgendaResponse], tags=["Citas"])
def profesionales_para_agenda(
    usuario: UsuarioLeerCitas,
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
) -> list[ProfesionalAgendaResponse]:
    """Profesionales activos de tu institucion con quienes se puede agendar (selector de citas)."""
    if contenedor.administracion is None or contenedor.cifrador is None:
        raise IntegracionNoConfigurada("La identidad central todavia no esta configurada.")
    lista = AdministrarProfesionales(contenedor.administracion, contenedor.cifrador).para_agenda(
        usuario
    )
    return [ProfesionalAgendaResponse.model_validate(p) for p in lista]
