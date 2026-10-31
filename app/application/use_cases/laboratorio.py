"""Ordenes de laboratorio: solicitar, tomar muestras, registrar resultados, validar, cancelar."""

from datetime import UTC, datetime

from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.errores import (
    ConflictoEstado,
    ConsultaNoEncontrada,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    RegistroNoEncontrado,
)
from app.domain.identidad import UsuarioAutenticado
from app.domain.laboratorio import (
    ESTADOS_ABIERTOS,
    EstadoOrden,
    NuevaMuestra,
    Orden,
    PruebaCatalogo,
    ResumenOrden,
    ValorResultado,
    VersionPrueba,
    construir_resultados,
)

MAXIMO_PRUEBAS_POR_ORDEN = 50


def _paciente(unidad, id_paciente: str, escribir: bool) -> None:
    paciente = unidad.pacientes.obtener_por_id(id_paciente)
    if paciente is None:
        raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
    if escribir and paciente.archivado:
        raise PacienteArchivado("El historial esta archivado; no admite cambios.")


def _orden_abierta(unidad, id_paciente: str, id_orden: str) -> Orden:
    orden = unidad.laboratorio.obtener(id_paciente, id_orden)
    if orden is None:
        raise RegistroNoEncontrado("La orden no existe en el historial del paciente.")
    if orden.estado not in ESTADOS_ABIERTOS:
        raise ConflictoEstado(f"Una orden {orden.estado.value} ya no se modifica.")
    return orden


class ConsultarCatalogoLaboratorio:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self) -> list[PruebaCatalogo]:
        with self.unidad_trabajo as unidad:
            return unidad.laboratorio.listar_catalogo()


class SolicitarOrden:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        usuario: UsuarioAutenticado,
        id_paciente: str,
        id_consulta: str,
        codigos: tuple[str, ...],
    ) -> Orden:
        if not codigos or len(codigos) > MAXIMO_PRUEBAS_POR_ORDEN:
            raise DatosInvalidos(f"Pide entre 1 y {MAXIMO_PRUEBAS_POR_ORDEN} pruebas.")
        if len(set(codigos)) != len(codigos):
            raise DatosInvalidos("Una prueba no puede repetirse en la misma orden.")
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=True)
            if unidad.historial.obtener_consulta(id_paciente, id_consulta) is None:
                raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")
            orden = unidad.laboratorio.solicitar(
                id_paciente, id_consulta, usuario.id_usuario, codigos
            )
            unidad.commit()
            return orden


class ConsultarOrdenes:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def listar(self, id_paciente: str, limite: int = 50) -> list[Orden]:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=False)
            return unidad.laboratorio.listar(id_paciente, limite)

    def una(self, id_paciente: str, id_orden: str) -> Orden:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=False)
            orden = unidad.laboratorio.obtener(id_paciente, id_orden)
            if orden is None:
                raise RegistroNoEncontrado("La orden no existe en el historial del paciente.")
            return orden


class RegistrarMuestra:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, id_paciente: str, id_orden: str, muestra: NuevaMuestra) -> Orden:
        ahora = datetime.now(UTC)
        if muestra.tomada_en is not None and muestra.tomada_en > ahora:
            raise DatosInvalidos("La muestra no puede tomarse en el futuro.")
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=True)
            _orden_abierta(unidad, id_paciente, id_orden)
            orden = unidad.laboratorio.registrar_muestra(id_paciente, id_orden, muestra, ahora)
            unidad.commit()
            return orden


class RegistrarResultados:
    """Captura o corrige los resultados de una prueba mientras la orden siga abierta."""

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        usuario: UsuarioAutenticado,
        id_paciente: str,
        id_orden: str,
        codigo_prueba: str,
        valores: tuple[ValorResultado, ...],
        observaciones: str | None,
    ) -> Orden:
        if not valores:
            raise DatosInvalidos("Registra al menos un resultado.")
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=True)
            orden = _orden_abierta(unidad, id_paciente, id_orden)
            prueba = next((p for p in orden.pruebas if p.codigo == codigo_prueba), None)
            if prueba is None:
                raise RegistroNoEncontrado("Esa prueba no forma parte de la orden.")
            resultados = construir_resultados(prueba, valores)
            actualizada = unidad.laboratorio.registrar_resultados(
                id_paciente,
                id_orden,
                codigo_prueba,
                resultados,
                observaciones,
                usuario.id_usuario,
                datetime.now(UTC),
            )
            unidad.commit()
            return actualizada


class ValidarOrden:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, usuario: UsuarioAutenticado, id_paciente: str, id_orden: str) -> Orden:
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=True)
            orden = _orden_abierta(unidad, id_paciente, id_orden)
            if not orden.lista_para_validar:
                raise DatosInvalidos("Faltan resultados: cada prueba necesita al menos uno.")
            validada = unidad.laboratorio.validar(
                id_paciente, id_orden, usuario.id_usuario, datetime.now(UTC)
            )
            unidad.commit()
            return validada


class CancelarOrden:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self, usuario: UsuarioAutenticado, id_paciente: str, id_orden: str, motivo: str
    ) -> Orden:
        if not motivo.strip():
            raise DatosInvalidos("Para cancelar una orden indica el motivo.")
        with self.unidad_trabajo as unidad:
            _paciente(unidad, id_paciente, escribir=True)
            _orden_abierta(unidad, id_paciente, id_orden)
            cancelada = unidad.laboratorio.cancelar(
                id_paciente, id_orden, motivo, usuario.id_usuario, datetime.now(UTC)
            )
            unidad.commit()
            return cancelada


class TableroLaboratorio:
    """Ordenes de toda la institucion: cola de trabajo y atajo "registrar resultados"."""

    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(
        self,
        estados: frozenset[EstadoOrden] | None = None,
        limite: int = 50,
        antes_de: datetime | None = None,
        antes_de_id: str | None = None,
    ) -> list[ResumenOrden]:
        if antes_de_id is not None and antes_de is None:
            raise DatosInvalidos("antes_de_id requiere antes_de.")
        with self.unidad_trabajo as unidad:
            return unidad.laboratorio.listar_institucion(estados, limite, antes_de, antes_de_id)


class ResumenDelLaboratorio:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo):
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self):
        with self.unidad_trabajo as unidad:
            return unidad.laboratorio.resumen()


class VersionesDePrueba:
    def __init__(self, unidad_trabajo: UnidadDeTrabajo) -> None:
        self.unidad_trabajo = unidad_trabajo

    def ejecutar(self, codigo: str) -> list[VersionPrueba]:
        with self.unidad_trabajo as unidad:
            versiones = unidad.laboratorio.versiones(codigo)
        if not versiones:
            raise RegistroNoEncontrado("Esa prueba no existe en el catalogo.")
        return versiones
