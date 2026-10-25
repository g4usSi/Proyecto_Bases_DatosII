from dataclasses import replace
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.application.use_cases.actualizar_paciente import ActualizarPaciente, AgregarAlergias
from app.application.use_cases.agregar_a_consulta import AgregarAConsulta, ConsultarConsulta
from app.application.use_cases.archivar_paciente import ArchivarPaciente
from app.application.use_cases.buscar_pacientes import BuscarPacientes
from app.application.use_cases.citas import CitasDePaciente
from app.application.use_cases.consultar_historial import ConsultarHistorial
from app.application.use_cases.consultar_paciente import ConsultarPaciente
from app.application.use_cases.registrar_consulta import RegistrarConsulta
from app.application.use_cases.registrar_paciente import RegistrarPaciente
from app.domain import permisos
from app.domain.consulta import Adenda, Diagnostico, NuevaConsulta, Receta, Tratamiento
from app.domain.identidad import UsuarioAutenticado
from app.domain.paciente import CambiosPaciente, NuevoPaciente, Paciente
from app.presentation.api.dependencies import (
    ContextoArchivar,
    ContextoLeerCitas,
    ContextoLeerHistorial,
    ContextoLeerPaciente,
    ContextoRegistrarConsulta,
    ContextoRegistrarPaciente,
)
from app.presentation.api.schemas.cita import CitaResponse
from app.presentation.api.schemas.historial import (
    AdendaCrear,
    ConsultaCrear,
    ConsultaResponse,
    HistorialResponse,
)
from app.presentation.api.schemas.paciente import (
    AlergiasAgregar,
    ArchivoCrear,
    ArchivoResponse,
    PacienteActualizar,
    PacienteCrear,
    PacienteResponse,
    PacienteResumen,
)

router = APIRouter(prefix="/pacientes", tags=["Pacientes"])

IdPaciente = Annotated[str, Path(min_length=1, max_length=128)]
IdConsulta = Annotated[str, Path(min_length=1, max_length=128)]


def respuesta_paciente(paciente: Paciente, usuario: UsuarioAutenticado) -> PacienteResponse:
    """Las alergias son informacion clinica: solo se muestran con historiales:leer."""
    if permisos.HISTORIALES_LEER not in usuario.permisos:
        paciente = replace(paciente, alergias=None)
    return PacienteResponse.model_validate(paciente)


@router.post("", response_model=PacienteResponse, status_code=status.HTTP_201_CREATED)
def registrar_paciente(
    datos: PacienteCrear, contexto: ContextoRegistrarPaciente
) -> PacienteResponse:
    """Abre un historial nuevo en el motor de la institucion del usuario."""
    paciente = RegistrarPaciente(contexto.unidad).ejecutar(
        NuevoPaciente(
            datos.nombres,
            datos.apellidos,
            datos.fecha_nacimiento,
            datos.contacto.a_dominio() if datos.contacto else None,
            (tuple(a.a_dominio() for a in datos.alergias) if datos.alergias is not None else None),
        )
    )
    return respuesta_paciente(paciente, contexto.usuario)


@router.get("", response_model=list[PacienteResumen])
def buscar_pacientes(
    nombre: Annotated[str, Query(min_length=2, max_length=300, description="Nombre o apellido")],
    contexto: ContextoLeerPaciente,
    limite: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[PacienteResumen]:
    """Busca por comienzo de palabra, sin importar mayusculas ni acentos."""
    pacientes = BuscarPacientes(contexto.unidad).ejecutar(nombre, limite)
    return [PacienteResumen.model_validate(p) for p in pacientes]


@router.get("/{id_paciente}", response_model=PacienteResponse)
def consultar_paciente(id_paciente: IdPaciente, contexto: ContextoLeerPaciente) -> PacienteResponse:
    paciente = ConsultarPaciente(contexto.unidad).ejecutar(id_paciente)
    return respuesta_paciente(paciente, contexto.usuario)


@router.patch("/{id_paciente}", response_model=PacienteResponse)
def actualizar_paciente(
    id_paciente: IdPaciente, datos: PacienteActualizar, contexto: ContextoRegistrarPaciente
) -> PacienteResponse:
    """Corrige nombre, fecha de nacimiento o contacto. 409 si el historial esta archivado."""
    paciente = ActualizarPaciente(contexto.unidad).ejecutar(
        id_paciente,
        CambiosPaciente(
            datos.nombres,
            datos.apellidos,
            datos.fecha_nacimiento,
            datos.contacto.a_dominio() if datos.contacto else None,
        ),
    )
    return respuesta_paciente(paciente, contexto.usuario)


@router.post("/{id_paciente}/alergias", response_model=PacienteResponse)
def agregar_alergias(
    id_paciente: IdPaciente, datos: AlergiasAgregar, contexto: ContextoRegistrarPaciente
) -> PacienteResponse:
    """Agrega alergias al historial. Nunca borra ni edita las ya registradas."""
    paciente = AgregarAlergias(contexto.unidad).ejecutar(
        id_paciente, tuple(a.a_dominio() for a in datos.alergias)
    )
    return respuesta_paciente(paciente, contexto.usuario)


@router.get("/{id_paciente}/citas", response_model=list[CitaResponse])
def citas_del_paciente(
    id_paciente: IdPaciente,
    contexto: ContextoLeerCitas,
    limite: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[CitaResponse]:
    citas = CitasDePaciente(contexto.unidad).ejecutar(id_paciente, limite)
    return [CitaResponse.model_validate(c) for c in citas]


@router.get("/{id_paciente}/historial", response_model=HistorialResponse)
def consultar_historial(
    id_paciente: IdPaciente,
    contexto: ContextoLeerHistorial,
    limite: Annotated[int, Query(ge=1, le=100)] = 20,
    antes_de: Annotated[datetime | None, Query()] = None,
) -> HistorialResponse:
    """Consultas de la mas reciente a la mas antigua, paginadas por cursor."""
    historial = ConsultarHistorial(contexto.unidad).ejecutar(id_paciente, limite, antes_de)
    return HistorialResponse(
        paciente=PacienteResponse.model_validate(historial.paciente),
        consultas=[ConsultaResponse.model_validate(c) for c in historial.consultas],
        siguiente_antes_de=historial.siguiente_antes_de,
    )


@router.post(
    "/{id_paciente}/consultas",
    response_model=ConsultaResponse,
    status_code=status.HTTP_201_CREATED,
)
def registrar_consulta(
    id_paciente: IdPaciente, datos: ConsultaCrear, contexto: ContextoRegistrarConsulta
) -> ConsultaResponse:
    """Consulta + diagnosticos + tratamientos + recetas en una sola operacion atomica."""
    nueva = NuevaConsulta(
        motivo=datos.motivo,
        notas=datos.notas,
        diagnosticos=tuple(Diagnostico(**d.model_dump()) for d in datos.diagnosticos),
        tratamientos=tuple(Tratamiento(**t.model_dump()) for t in datos.tratamientos),
        recetas=tuple(Receta(**r.model_dump()) for r in datos.recetas),
    )
    consulta = RegistrarConsulta(contexto.unidad).ejecutar(contexto.usuario, id_paciente, nueva)
    return ConsultaResponse.model_validate(consulta)


@router.get("/{id_paciente}/consultas/{id_consulta}", response_model=ConsultaResponse)
def consultar_consulta(
    id_paciente: IdPaciente, id_consulta: IdConsulta, contexto: ContextoLeerHistorial
) -> ConsultaResponse:
    consulta = ConsultarConsulta(contexto.unidad).ejecutar(id_paciente, id_consulta)
    return ConsultaResponse.model_validate(consulta)


@router.post("/{id_paciente}/consultas/{id_consulta}/adenda", response_model=ConsultaResponse)
def agregar_a_consulta(
    id_paciente: IdPaciente,
    id_consulta: IdConsulta,
    datos: AdendaCrear,
    contexto: ContextoRegistrarConsulta,
) -> ConsultaResponse:
    """Agrega diagnosticos, tratamientos, recetas o una nota a una consulta ya guardada.

    Solo agrega (nunca edita ni borra) y es atomica. Quien agrega y cuando queda anotado
    en las notas de la consulta; asi se rectifica sin perder lo original.
    """
    adenda = Adenda(
        nota=datos.nota,
        diagnosticos=tuple(Diagnostico(**d.model_dump()) for d in datos.diagnosticos),
        tratamientos=tuple(Tratamiento(**t.model_dump()) for t in datos.tratamientos),
        recetas=tuple(Receta(**r.model_dump()) for r in datos.recetas),
    )
    consulta = AgregarAConsulta(contexto.unidad).ejecutar(
        contexto.usuario, id_paciente, id_consulta, adenda
    )
    return ConsultaResponse.model_validate(consulta)


@router.post("/{id_paciente}/archivo", response_model=ArchivoResponse)
def archivar_paciente(
    id_paciente: IdPaciente, datos: ArchivoCrear, contexto: ContextoArchivar
) -> ArchivoResponse:
    """Baja por traslado, fallecimiento u otra causa. El historial se conserva."""
    baja = ArchivarPaciente(contexto.unidad).ejecutar(
        contexto.usuario, id_paciente, datos.motivo, datos.detalle
    )
    return ArchivoResponse.model_validate(baja)
