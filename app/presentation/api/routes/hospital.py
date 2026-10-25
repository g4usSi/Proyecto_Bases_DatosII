"""Hospital General: camas, ingresos (emergencias, programados, traslados), ordenes y resumen.

Otros establecimientos responden 501. Ver documentacion-backend.md.
"""

from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Path, Query, Request, status

from app.application.use_cases.hospital import (
    AgregarDiagnosticoIngreso,
    AgregarOrdenIngreso,
    CambiarEstadoCama,
    ConsultarCamas,
    ConsultarIngresos,
    DarDeAlta,
    IngresarPaciente,
    ResumenDelHospital,
)
from app.domain.consulta import Diagnostico, Receta
from app.domain.hospital import EstadoCama, NuevaOrdenMedica, NuevoIngreso, TipoIngreso
from app.presentation.api.dependencies import (
    ContextoGestionarCamas,
    ContextoLeerHistorial,
    ContextoLeerPaciente,
    ContextoRegistrarConsulta,
)
from app.presentation.api.schemas.historial import DiagnosticoSchema
from app.presentation.api.schemas.hospital import (
    AltaCrear,
    CamaResponse,
    EstadoCamaCambio,
    IngresoCrear,
    IngresoResponse,
    OrdenMedicaCrear,
    ResumenHospitalResponse,
)

router = APIRouter(tags=["Hospital"])

IdPaciente = Annotated[str, Path(min_length=1, max_length=128)]
IdIngreso = Annotated[str, Path(min_length=1, max_length=20)]
IdCama = Annotated[int, Path(ge=1, le=2_147_483_647)]
RUTA_INGRESO = "/pacientes/{id_paciente}/ingresos/{id_ingreso}"


def _diagnostico(d: DiagnosticoSchema) -> Diagnostico:
    return Diagnostico(d.descripcion, d.codigo, d.sistema_codigo)


@router.get("/camas", response_model=list[CamaResponse])
def listar_camas(
    contexto: ContextoLeerPaciente,
    id_departamento: Annotated[int | None, Query(ge=1)] = None,
    estado: EstadoCama | None = None,
) -> list[CamaResponse]:
    """Camas con su estado y, si esta ocupada, el paciente ingresado."""
    camas = ConsultarCamas(contexto.unidad).ejecutar(id_departamento, estado)
    return [CamaResponse.model_validate(c) for c in camas]


@router.post("/camas/{id_cama}/estado", response_model=CamaResponse)
def cambiar_estado_cama(
    id_cama: IdCama, datos: EstadoCamaCambio, contexto: ContextoGestionarCamas
) -> CamaResponse:
    """Disponible, limpieza o mantenimiento. 409 si tiene un paciente ingresado."""
    return CamaResponse.model_validate(
        CambiarEstadoCama(contexto.unidad).ejecutar(id_cama, datos.estado)
    )


@router.get("/ingresos", response_model=list[IngresoResponse])
def tablero_de_ingresos(
    contexto: ContextoLeerHistorial,
    abiertos: Annotated[
        bool | None, Query(description="true: internados ahora; false: con alta; omitir: todos")
    ] = True,
    tipo: TipoIngreso | None = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[IngresoResponse]:
    """Ingresos de todo el hospital (emergencias y hospitalizacion), mas recientes primero."""
    ingresos = ConsultarIngresos(contexto.unidad).tablero(abiertos, tipo, limite)
    return [IngresoResponse.model_validate(i) for i in ingresos]


@router.post(
    "/pacientes/{id_paciente}/ingresos",
    response_model=IngresoResponse,
    status_code=status.HTTP_201_CREATED,
)
def ingresar_paciente(
    id_paciente: IdPaciente, datos: IngresoCrear, contexto: ContextoRegistrarConsulta
) -> IngresoResponse:
    """Ingresa al paciente en una cama disponible. 409 si la cama no esta disponible o el
    paciente ya esta ingresado; 409 si el historial esta archivado."""
    ingreso = IngresarPaciente(contexto.unidad).ejecutar(
        contexto.usuario,
        id_paciente,
        NuevoIngreso(
            datos.id_cama,
            datos.tipo,
            datos.motivo,
            tuple(_diagnostico(d) for d in datos.diagnosticos),
        ),
    )
    return IngresoResponse.model_validate(ingreso)


@router.get("/pacientes/{id_paciente}/ingresos", response_model=list[IngresoResponse])
def ingresos_del_paciente(
    id_paciente: IdPaciente,
    contexto: ContextoLeerHistorial,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[IngresoResponse]:
    ingresos = ConsultarIngresos(contexto.unidad).del_paciente(id_paciente, limite)
    return [IngresoResponse.model_validate(i) for i in ingresos]


@router.get(RUTA_INGRESO, response_model=IngresoResponse)
def consultar_ingreso(
    id_paciente: IdPaciente, id_ingreso: IdIngreso, contexto: ContextoLeerHistorial
) -> IngresoResponse:
    return IngresoResponse.model_validate(
        ConsultarIngresos(contexto.unidad).uno(id_paciente, id_ingreso)
    )


@router.post(RUTA_INGRESO + "/diagnosticos", response_model=IngresoResponse)
def agregar_diagnostico(
    id_paciente: IdPaciente,
    id_ingreso: IdIngreso,
    datos: DiagnosticoSchema,
    contexto: ContextoRegistrarConsulta,
) -> IngresoResponse:
    """Agrega un diagnostico mientras el paciente siga ingresado (solo agregar)."""
    ingreso = AgregarDiagnosticoIngreso(contexto.unidad).ejecutar(
        id_paciente, id_ingreso, _diagnostico(datos)
    )
    return IngresoResponse.model_validate(ingreso)


@router.post(RUTA_INGRESO + "/ordenes", response_model=IngresoResponse)
def agregar_orden(
    id_paciente: IdPaciente,
    id_ingreso: IdIngreso,
    datos: OrdenMedicaCrear,
    contexto: ContextoRegistrarConsulta,
) -> IngresoResponse:
    """Orden medica: medicamento (con recetas), examen, procedimiento o interconsulta."""
    orden = NuevaOrdenMedica(
        datos.tipo,
        datos.descripcion,
        tuple(
            Receta(
                r.medicamento,
                r.dosis,
                r.frecuencia,
                r.via_administracion,
                r.duracion_dias,
                r.instrucciones,
            )
            for r in datos.recetas
        ),
    )
    ingreso = AgregarOrdenIngreso(contexto.unidad).ejecutar(
        contexto.usuario, id_paciente, id_ingreso, orden
    )
    return IngresoResponse.model_validate(ingreso)


@router.post(RUTA_INGRESO + "/alta", response_model=IngresoResponse)
def dar_alta(
    id_paciente: IdPaciente,
    id_ingreso: IdIngreso,
    datos: AltaCrear,
    contexto: ContextoRegistrarConsulta,
) -> IngresoResponse:
    """Cierra el ingreso (una sola vez; 409 si ya tenia alta) y deja la cama en limpieza."""
    ingreso = DarDeAlta(contexto.unidad).ejecutar(id_paciente, id_ingreso, datos.motivo)
    return IngresoResponse.model_validate(ingreso)


@router.get("/hospital/resumen", response_model=ResumenHospitalResponse)
def resumen_del_hospital(
    request: Request, contexto: ContextoLeerPaciente
) -> ResumenHospitalResponse:
    """Tablero de inicio: ocupacion de camas, ingresos y citas del dia (solo conteos)."""
    zona = ZoneInfo(request.app.state.settings.zona_horaria)
    return ResumenHospitalResponse.model_validate(
        ResumenDelHospital(contexto.unidad, zona).ejecutar()
    )
