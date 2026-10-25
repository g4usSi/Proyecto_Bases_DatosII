from typing import Annotated

from fastapi import APIRouter, Path, Query, status
from pydantic import AwareDatetime

from app.application.use_cases.laboratorio import (
    CancelarOrden,
    ConsultarCatalogoLaboratorio,
    ConsultarOrdenes,
    RegistrarMuestra,
    RegistrarResultados,
    SolicitarOrden,
    TableroLaboratorio,
    ValidarOrden,
    VersionesDePrueba,
)
from app.domain.laboratorio import EstadoOrden, NuevaMuestra, ValorResultado
from app.presentation.api.dependencies import (
    ContextoLeerLab,
    ContextoRegistrarConsulta,
    ContextoResultadosLab,
    ContextoValidarLab,
)
from app.presentation.api.schemas.laboratorio import (
    CancelarOrdenCrear,
    MuestraCrear,
    OrdenCrear,
    OrdenResponse,
    PruebaCatalogoResponse,
    ResultadosCrear,
    ResumenOrdenResponse,
    VersionPruebaResponse,
)

router = APIRouter(tags=["Laboratorio"])

IdPaciente = Annotated[str, Path(min_length=1, max_length=128)]
IdOrden = Annotated[str, Path(min_length=1, max_length=128)]
CodigoPrueba = Annotated[str, Path(min_length=1, max_length=64)]


@router.get("/laboratorio/pruebas", response_model=list[PruebaCatalogoResponse])
def catalogo_de_pruebas(contexto: ContextoLeerLab) -> list[PruebaCatalogoResponse]:
    """Pruebas activas del catalogo (solo Laboratorio Clinico)."""
    pruebas = ConsultarCatalogoLaboratorio(contexto.unidad).ejecutar()
    return [PruebaCatalogoResponse.model_validate(p) for p in pruebas]


@router.get("/laboratorio/pruebas/{codigo}/versiones", response_model=list[VersionPruebaResponse])
def versiones_de_prueba(
    codigo: CodigoPrueba, contexto: ContextoLeerLab
) -> list[VersionPruebaResponse]:
    """Todas las versiones publicadas de una prueba (la vigente marcada). 404 si no existe."""
    versiones = VersionesDePrueba(contexto.unidad).ejecutar(codigo)
    return [VersionPruebaResponse.model_validate(v) for v in versiones]


@router.get("/laboratorio/ordenes", response_model=list[ResumenOrdenResponse])
def tablero_de_ordenes(
    contexto: ContextoLeerLab,
    estado: Annotated[
        list[EstadoOrden] | None,
        Query(description="Repetible. Por ejemplo estado=solicitada&estado=en_proceso"),
    ] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    antes_de: Annotated[
        AwareDatetime | None,
        Query(description="Cursor: solicitada_en de la ultima fila recibida"),
    ] = None,
) -> list[ResumenOrdenResponse]:
    """Ordenes de toda tu institucion, de la mas reciente a la mas antigua (tablero)."""
    filas = TableroLaboratorio(contexto.unidad).ejecutar(
        frozenset(estado) if estado else None, limite, antes_de
    )
    return [ResumenOrdenResponse.model_validate(f) for f in filas]


@router.post(
    "/pacientes/{id_paciente}/ordenes",
    response_model=OrdenResponse,
    status_code=status.HTTP_201_CREATED,
)
def solicitar_orden(
    id_paciente: IdPaciente, datos: OrdenCrear, contexto: ContextoRegistrarConsulta
) -> OrdenResponse:
    """Pide pruebas para una consulta del paciente; la orden guarda copia de cada prueba."""
    orden = SolicitarOrden(contexto.unidad).ejecutar(
        contexto.usuario, id_paciente, datos.id_consulta, tuple(datos.pruebas)
    )
    return OrdenResponse.model_validate(orden)


@router.get("/pacientes/{id_paciente}/ordenes", response_model=list[OrdenResponse])
def listar_ordenes(
    id_paciente: IdPaciente,
    contexto: ContextoLeerLab,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[OrdenResponse]:
    ordenes = ConsultarOrdenes(contexto.unidad).listar(id_paciente, limite)
    return [OrdenResponse.model_validate(o) for o in ordenes]


@router.get("/pacientes/{id_paciente}/ordenes/{id_orden}", response_model=OrdenResponse)
def consultar_orden(
    id_paciente: IdPaciente, id_orden: IdOrden, contexto: ContextoLeerLab
) -> OrdenResponse:
    return OrdenResponse.model_validate(
        ConsultarOrdenes(contexto.unidad).una(id_paciente, id_orden)
    )


@router.post("/pacientes/{id_paciente}/ordenes/{id_orden}/muestras", response_model=OrdenResponse)
def registrar_muestra(
    id_paciente: IdPaciente,
    id_orden: IdOrden,
    datos: MuestraCrear,
    contexto: ContextoResultadosLab,
) -> OrdenResponse:
    orden = RegistrarMuestra(contexto.unidad).ejecutar(
        id_paciente,
        id_orden,
        NuevaMuestra(datos.tipo, datos.tomada_en, datos.condicion, datos.observaciones),
    )
    return OrdenResponse.model_validate(orden)


@router.put(
    "/pacientes/{id_paciente}/ordenes/{id_orden}/pruebas/{codigo}/resultados",
    response_model=OrdenResponse,
)
def registrar_resultados(
    id_paciente: IdPaciente,
    id_orden: IdOrden,
    codigo: CodigoPrueba,
    datos: ResultadosCrear,
    contexto: ContextoResultadosLab,
) -> OrdenResponse:
    """Captura (o corrige, mientras la orden no este validada) los resultados de una prueba."""
    orden = RegistrarResultados(contexto.unidad).ejecutar(
        contexto.usuario,
        id_paciente,
        id_orden,
        codigo,
        tuple(ValorResultado(v.codigo_parametro, v.valor) for v in datos.valores),
        datos.observaciones,
    )
    return OrdenResponse.model_validate(orden)


@router.post("/pacientes/{id_paciente}/ordenes/{id_orden}/validar", response_model=OrdenResponse)
def validar_orden(
    id_paciente: IdPaciente, id_orden: IdOrden, contexto: ContextoValidarLab
) -> OrdenResponse:
    """Cierra la orden: despues de validada ya no se modifica."""
    orden = ValidarOrden(contexto.unidad).ejecutar(contexto.usuario, id_paciente, id_orden)
    return OrdenResponse.model_validate(orden)


@router.post("/pacientes/{id_paciente}/ordenes/{id_orden}/cancelar", response_model=OrdenResponse)
def cancelar_orden(
    id_paciente: IdPaciente,
    id_orden: IdOrden,
    datos: CancelarOrdenCrear,
    contexto: ContextoRegistrarConsulta,
) -> OrdenResponse:
    orden = CancelarOrden(contexto.unidad).ejecutar(
        contexto.usuario, id_paciente, id_orden, datos.motivo
    )
    return OrdenResponse.model_validate(orden)
