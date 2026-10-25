"""Casos de uso del Hospital General (otros motores responden 501 desde el adaptador).

Reglas comunes: el paciente debe existir (404) y no estar archivado (409) para ingresar;
un ingreso con alta ya no admite cambios (409); nada se borra.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.consulta import Diagnostico
from app.domain.errores import (
    ConflictoEstado,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    RegistroNoEncontrado,
)
from app.domain.hospital import (
    ESTADOS_CAMA_MANUALES,
    Cama,
    Departamento,
    EstadoCama,
    Ingreso,
    NuevaOrdenMedica,
    NuevoIngreso,
    ResumenHospital,
    TipoIngreso,
)
from app.domain.identidad import UsuarioAutenticado


def _paciente_existe(unidad: UnidadDeTrabajo, id_paciente: str, activo: bool) -> None:
    paciente = unidad.pacientes.obtener_por_id(id_paciente)
    if paciente is None:
        raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
    if activo and paciente.archivado:
        raise PacienteArchivado("El historial esta archivado; no admite cambios.")


class ConsultarDepartamentos:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self) -> list[Departamento]:
        with self.unidad_trabajo as unidad:
            return unidad.hospital.listar_departamentos()


class ConsultarCamas:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self, id_departamento: int | None = None, estado: EstadoCama | None = None
    ) -> list[Cama]:
        with self.unidad_trabajo as unidad:
            return unidad.hospital.listar_camas(id_departamento, estado)


class CambiarEstadoCama:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_cama: int, estado: EstadoCama) -> Cama:
        if estado not in ESTADOS_CAMA_MANUALES:
            raise DatosInvalidos("Una cama queda ocupada solo al ingresar a un paciente.")
        with self.unidad_trabajo as unidad:
            cama = unidad.hospital.obtener_cama(id_cama)
            if cama is None:
                raise RegistroNoEncontrado("La cama no existe.")
            if cama.ocupante is not None:
                raise ConflictoEstado("La cama tiene un paciente ingresado: da el alta primero.")
            cambiada = unidad.hospital.cambiar_estado_cama(id_cama, estado)
            unidad.commit()
            return cambiada


class IngresarPaciente:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self, usuario: UsuarioAutenticado, id_paciente: str, datos: NuevoIngreso
    ) -> Ingreso:
        if not datos.motivo.strip():
            raise DatosInvalidos("Indica el motivo del ingreso.")
        with self.unidad_trabajo as unidad:
            _paciente_existe(unidad, id_paciente, activo=True)
            ingreso = unidad.hospital.ingresar(
                id_paciente, usuario.id_usuario, datos, datetime.now(UTC)
            )
            unidad.commit()
            return ingreso


class ConsultarIngresos:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def tablero(
        self, abiertos: bool | None = True, tipo: TipoIngreso | None = None, limite: int = 100
    ) -> list[Ingreso]:
        with self.unidad_trabajo as unidad:
            return unidad.hospital.listar_ingresos(None, abiertos, tipo, limite)

    def del_paciente(self, id_paciente: str, limite: int = 50) -> list[Ingreso]:
        with self.unidad_trabajo as unidad:
            _paciente_existe(unidad, id_paciente, activo=False)
            return unidad.hospital.listar_ingresos(id_paciente, None, None, limite)

    def uno(self, id_paciente: str, id_ingreso: str) -> Ingreso:
        with self.unidad_trabajo as unidad:
            _paciente_existe(unidad, id_paciente, activo=False)
            ingreso = unidad.hospital.obtener_ingreso(id_paciente, id_ingreso)
            if ingreso is None:
                raise RegistroNoEncontrado("El ingreso no existe en el historial del paciente.")
            return ingreso


class AgregarDiagnosticoIngreso:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_ingreso: str, diagnostico: Diagnostico) -> Ingreso:
        with self.unidad_trabajo as unidad:
            _paciente_existe(unidad, id_paciente, activo=True)
            ingreso = unidad.hospital.agregar_diagnostico(id_paciente, id_ingreso, diagnostico)
            unidad.commit()
            return ingreso


class AgregarOrdenIngreso:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        usuario: UsuarioAutenticado,
        id_paciente: str,
        id_ingreso: str,
        orden: NuevaOrdenMedica,
    ) -> Ingreso:
        orden.validar()
        with self.unidad_trabajo as unidad:
            _paciente_existe(unidad, id_paciente, activo=True)
            ingreso = unidad.hospital.agregar_orden(
                id_paciente, id_ingreso, usuario.id_usuario, orden, datetime.now(UTC)
            )
            unidad.commit()
            return ingreso


class DarDeAlta:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_ingreso: str, motivo: str) -> Ingreso:
        if not motivo.strip():
            raise DatosInvalidos("Indica el motivo del alta.")
        with self.unidad_trabajo as unidad:
            # El alta se permite aunque el historial se haya archivado: cierra la estancia.
            _paciente_existe(unidad, id_paciente, activo=False)
            ingreso = unidad.hospital.dar_alta(id_paciente, id_ingreso, motivo, datetime.now(UTC))
            unidad.commit()
            return ingreso


class ResumenDelHospital:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo, zona: ZoneInfo) -> None:
        self.unidad_trabajo = unidad_trabajo
        self.zona = zona

    def ejecutar(self) -> ResumenHospital:
        hoy = datetime.now(self.zona).date()
        with self.unidad_trabajo as unidad:
            return unidad.hospital.resumen(hoy)
