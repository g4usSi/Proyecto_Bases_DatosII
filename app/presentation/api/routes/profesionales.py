"""Administracion del personal (cuenta de administracion de cada institucion).

La institucion sale siempre del token del administrador. Las respuestas que muestran una
contrasena generada llevan Cache-Control: no-store y no se repiten.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status

from app.application.errores import IntegracionNoConfigurada
from app.application.use_cases.hospital import ConsultarDepartamentos
from app.application.use_cases.profesionales import AdministrarProfesionales
from app.bootstrap.container import Contenedor
from app.domain.administracion import CambiosProfesional, EstadoCuenta, NuevoProfesional
from app.presentation.api.dependencies import (
    AdministradorDeProfesionales,
    ContextoDepartamentos,
    UsuarioLeerCitas,
    obtener_contenedor,
)
from app.presentation.api.schemas.profesionales import (
    ContrasenaRestablecidaResponse,
    DepartamentoResponse,
    ProfesionalAgendaResponse,
    ProfesionalCambiadoResponse,
    ProfesionalCambios,
    ProfesionalCreadoResponse,
    ProfesionalCrear,
    ProfesionalResponse,
)

router = APIRouter(tags=["Profesionales"])

IdProfesional = Annotated[str, Path(min_length=1, max_length=64)]
SIN_CACHE = {"Cache-Control": "no-store"}


def caso_de_uso(
    contenedor: Annotated[Contenedor, Depends(obtener_contenedor)],
    admin: AdministradorDeProfesionales,
) -> AdministrarProfesionales:
    if contenedor.administracion is None or contenedor.cifrador is None:
        raise IntegracionNoConfigurada("La identidad central todavia no esta configurada.")
    institucion = admin.institucion
    abrir = (
        (lambda: contenedor.crear_unidad_trabajo(institucion))
        if institucion in contenedor.unidades_trabajo
        else None
    )
    return AdministrarProfesionales(contenedor.administracion, contenedor.cifrador, abrir)


CasoDeUso = Annotated[AdministrarProfesionales, Depends(caso_de_uso)]


@router.post(
    "/profesionales",
    response_model=ProfesionalCreadoResponse,
    status_code=status.HTTP_201_CREATED,
)
def crear_profesional(
    datos: ProfesionalCrear,
    response: Response,
    admin: AdministradorDeProfesionales,
    casos: CasoDeUso,
) -> ProfesionalCreadoResponse:
    """Alta de un profesional en TU institucion. 409 si el correo ya existe."""
    resultado = casos.crear(
        admin,
        NuevoProfesional(
            datos.correo,
            datos.nombres,
            datos.apellidos,
            datos.rol,
            frozenset(datos.permisos) if datos.permisos is not None else None,
            datos.id_departamento,
        ),
        datos.contrasena_inicial.get_secret_value() if datos.contrasena_inicial else None,
    )
    response.headers.update(SIN_CACHE)
    return ProfesionalCreadoResponse(
        profesional=ProfesionalResponse.model_validate(resultado.ficha),
        vinculado=resultado.vinculado,
        contrasena_temporal=resultado.contrasena_temporal,
    )


@router.get("/profesionales", response_model=list[ProfesionalResponse])
def listar_profesionales(
    admin: AdministradorDeProfesionales,
    casos: CasoDeUso,
    rol: Annotated[str | None, Query(max_length=40)] = None,
    id_departamento: Annotated[int | None, Query(ge=1)] = None,
    estado: EstadoCuenta | None = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[ProfesionalResponse]:
    """Personal de tu institucion (sin cuentas de administracion), por apellidos."""
    fichas = casos.listar(admin, rol, id_departamento, estado, limite)
    return [ProfesionalResponse.model_validate(f) for f in fichas]


@router.get("/profesionales/{id_profesional}", response_model=ProfesionalResponse)
def consultar_profesional(
    id_profesional: IdProfesional, admin: AdministradorDeProfesionales, casos: CasoDeUso
) -> ProfesionalResponse:
    return ProfesionalResponse.model_validate(casos.obtener(admin, id_profesional))


@router.patch("/profesionales/{id_profesional}", response_model=ProfesionalCambiadoResponse)
def cambiar_profesional(
    id_profesional: IdProfesional,
    datos: ProfesionalCambios,
    admin: AdministradorDeProfesionales,
    casos: CasoDeUso,
) -> ProfesionalCambiadoResponse:
    """Area, permisos (lista completa), estado o nombre. Bloquear/desactivar corta el acceso
    de inmediato: sus sesiones abiertas dejan de valer."""
    enviados = datos.model_fields_set
    cambios = CambiosProfesional(
        nombres=datos.nombres,
        apellidos=datos.apellidos,
        permisos=frozenset(datos.permisos) if datos.permisos is not None else None,
        estado=datos.estado,
        id_departamento=datos.id_departamento,
        quitar_departamento="id_departamento" in enviados and datos.id_departamento is None,
    )
    resultado = casos.actualizar(admin, id_profesional, cambios)
    return ProfesionalCambiadoResponse(
        profesional=ProfesionalResponse.model_validate(resultado.ficha),
        vinculado=resultado.vinculado,
    )


@router.post(
    "/profesionales/{id_profesional}/restablecer-contrasena",
    response_model=ContrasenaRestablecidaResponse,
)
def restablecer_contrasena(
    id_profesional: IdProfesional,
    response: Response,
    admin: AdministradorDeProfesionales,
    casos: CasoDeUso,
) -> ContrasenaRestablecidaResponse:
    """Genera una contrasena nueva. El servidor la muestra UNA sola vez."""
    nueva = casos.restablecer_contrasena(admin, id_profesional)
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
