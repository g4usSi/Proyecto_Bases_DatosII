"""Clinica Odontologica en Cloud Firestore. Modelo completo en docs/modelo_odontologia.md.

    pacientes/{id}                         datos, contacto y alergias embebidos
    pacientes/{id}/consultas/{id}          diagnosticos/tratamientos/recetas embebidos
    pacientes/{id}/odontograma/actual      mapa de piezas FDI
    profesionales/{uuid_central}           perfil local, sin credenciales
    citas/{id}                             agenda (copia del nombre del paciente)
    agendas/{uuid}_{AAAA-MM-DD}            horarios ocupados de un profesional en un dia

Consistencia:
- Altas simples (paciente, pieza del odontograma) van a un WriteBatch que se
  confirma en commit(): se aplica completo o no se aplica.
- Operaciones que deben LEER antes de escribir (consulta en paciente activo,
  archivar, agendar sin choques, cambiar estado de cita) usan una transaccion de
  Firestore dentro del metodo: si otro usuario cambia lo leido, Firestore reintenta.
"""

import logging
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from types import TracebackType
from typing import Any, Literal, Self
from zoneinfo import ZoneInfo

from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError
from google.cloud import firestore
from google.cloud.firestore import Client, DocumentReference, Transaction, WriteBatch
from google.cloud.firestore_v1.base_query import FieldFilter

from app.application.errores import IntegracionNoConfigurada
from app.domain import busqueda
from app.domain.cita import ESTADOS_OCUPAN_HORARIO, TRANSICIONES, Cita, EstadoCita, NuevaCita
from app.domain.consulta import (
    Adenda,
    Consulta,
    Diagnostico,
    NuevaConsulta,
    Receta,
    Tratamiento,
)
from app.domain.errores import (
    CitaNoEncontrada,
    ConflictoAgenda,
    ConsultaNoEncontrada,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
)
from app.domain.odontograma import EstadoDental, EstadoPieza, Odontograma, Superficie
from app.domain.paciente import (
    Alergia,
    Baja,
    CambiosPaciente,
    Contacto,
    NuevoPaciente,
    Paciente,
)
from app.domain.profesional import ProfesionalLocal
from app.infrastructure.persistence.pendiente import repositorios_pendientes

logger = logging.getLogger(__name__)

MOTOR = "Firestore"
COLECCION_PACIENTES = "pacientes"
SUBCOLECCION_CONSULTAS = "consultas"
COLECCION_PROFESIONALES = "profesionales"
COLECCION_CITAS = "citas"
COLECCION_AGENDAS = "agendas"
MAX_CANDIDATOS_BUSQUEDA = 200
ERRORES_FIRESTORE = (GoogleAPIError, GoogleAuthError)
MAXIMO_AGENDA = 500


def _fecha(valor: Any) -> date | None:
    """Acepta texto ISO (formato del adaptador) o Timestamp creado desde la consola."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            return None
    return None


def _id_valido(identificador: str) -> bool:
    # Reglas de IDs de Firestore: sin "/", distinto de "." y "..", sin forma __x__.
    return (
        bool(identificador)
        and "/" not in identificador
        and identificador not in {".", ".."}
        and not (identificador.startswith("__") and identificador.endswith("__"))
    )


def _sin_nulos(valores: dict[str, Any]) -> dict[str, Any]:
    return {clave: valor for clave, valor in valores.items() if valor is not None}


class RepositorioPacientesFirestore:
    def __init__(self, unidad: "UnidadTrabajoFirestore") -> None:
        self.unidad = unidad

    def referencia(self, id_paciente: str) -> DocumentReference | None:
        if not _id_valido(id_paciente):
            return None
        return self.unidad.cliente.collection(COLECCION_PACIENTES).document(id_paciente)

    @staticmethod
    def a_paciente(id_paciente: str, datos: dict[str, Any]) -> Paciente:
        contacto = datos.get("contacto")
        return Paciente(
            id_paciente=id_paciente,
            nombres=datos.get("nombres", ""),
            apellidos=datos.get("apellidos", ""),
            fecha_nacimiento=_fecha(datos.get("fecha_nacimiento")),
            archivado=datos.get("estado") == "Archivado",
            contacto=(
                Contacto(
                    contacto.get("telefono"), contacto.get("correo"), contacto.get("direccion")
                )
                if contacto
                else None
            ),
            alergias=(
                tuple(
                    Alergia(a["sustancia"], a.get("reaccion"), a.get("severidad"))
                    for a in datos.get("alergias", [])
                )
                if datos.get("alergias_evaluadas")
                else None
            ),
        )

    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        referencia = self.referencia(id_paciente)
        if referencia is None:
            return None
        documento = referencia.get(timeout=self.unidad.timeout)
        if not documento.exists:
            return None
        return self.a_paciente(documento.id, documento.to_dict() or {})

    def registrar(self, datos: NuevoPaciente) -> Paciente:
        referencia = self.unidad.cliente.collection(COLECCION_PACIENTES).document()  # ID automatico
        self.unidad.lote.create(
            referencia,
            {
                "nombres": datos.nombres,
                "apellidos": datos.apellidos,
                # Firestore no tiene tipo "fecha sin hora"; texto ISO evita corrimientos de zona.
                "fecha_nacimiento": (
                    datos.fecha_nacimiento.isoformat() if datos.fecha_nacimiento else None
                ),
                # Embebidos: pocos datos, se leen siempre con el paciente.
                "contacto": _sin_nulos(asdict(datos.contacto)) if datos.contacto else None,
                "alergias_evaluadas": datos.alergias is not None,
                "alergias": [_sin_nulos(asdict(a)) for a in datos.alergias or ()],
                # Firestore no tiene LIKE: se guardan los comienzos de cada palabra del nombre
                # y se busca con array_contains (regla comun en domain/busqueda.py).
                "prefijos_nombre": busqueda.prefijos_de_nombre(datos.nombres, datos.apellidos),
                "estado": "Activo",
                "creado_en": firestore.SERVER_TIMESTAMP,
                "actualizado_en": firestore.SERVER_TIMESTAMP,
            },
        )
        return Paciente(
            referencia.id,
            datos.nombres,
            datos.apellidos,
            datos.fecha_nacimiento,
            contacto=datos.contacto,
            alergias=datos.alergias,
        )

    def buscar(self, palabras: tuple[str, ...], limite: int) -> list[Paciente]:
        # array_contains admite una sola palabra: la mas larga es la mas selectiva.
        # Las demas se comprueban en memoria. Se limita la lectura para no gastar cuota.
        principal = max(palabras, key=len)
        consulta = (
            self.unidad.cliente.collection(COLECCION_PACIENTES)
            .where(filter=FieldFilter("prefijos_nombre", "array_contains", principal))
            .limit(MAX_CANDIDATOS_BUSQUEDA)
        )
        encontrados = [
            self.a_paciente(d.id, d.to_dict() or {})
            for d in consulta.stream(timeout=self.unidad.timeout)
        ]
        coinciden = [p for p in encontrados if busqueda.coincide(palabras, p.nombres, p.apellidos)]
        coinciden.sort(
            key=lambda p: (
                busqueda.normalizar(p.apellidos),
                busqueda.normalizar(p.nombres),
                p.id_paciente,
            )
        )
        return coinciden[:limite]

    def actualizar(self, id_paciente: str, cambios: CambiosPaciente) -> None:
        referencia = self.referencia(id_paciente)
        if referencia is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if cambios.fecha_nacimiento is not None and cambios.fecha_nacimiento > date.today():
            raise DatosInvalidos("La fecha de nacimiento no puede ser futura.")

        @firestore.transactional
        def corregir(transaccion: Transaction) -> None:
            documento = referencia.get(transaction=transaccion)
            if not documento.exists:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            datos = documento.to_dict() or {}
            if datos.get("estado") == "Archivado":
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")
            nombres = cambios.nombres if cambios.nombres is not None else datos.get("nombres", "")
            apellidos = (
                cambios.apellidos if cambios.apellidos is not None else datos.get("apellidos", "")
            )
            poner: dict[str, Any] = {"actualizado_en": firestore.SERVER_TIMESTAMP}
            if cambios.nombres is not None or cambios.apellidos is not None:
                poner["nombres"], poner["apellidos"] = nombres, apellidos
                # La busqueda usa los prefijos guardados: se recalculan con el nombre nuevo.
                poner["prefijos_nombre"] = busqueda.prefijos_de_nombre(nombres, apellidos)
            if cambios.fecha_nacimiento is not None:
                poner["fecha_nacimiento"] = cambios.fecha_nacimiento.isoformat()
            if cambios.contacto is not None:  # reemplaza el contacto completo
                poner["contacto"] = _sin_nulos(asdict(cambios.contacto)) or firestore.DELETE_FIELD
            transaccion.update(referencia, poner)

        corregir(self.unidad.cliente.transaction())

    def agregar_alergias(self, id_paciente: str, alergias: tuple[Alergia, ...]) -> None:
        referencia = self.referencia(id_paciente)
        if referencia is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")

        @firestore.transactional
        def agregar(transaccion: Transaction) -> None:
            documento = referencia.get(transaction=transaccion)
            if not documento.exists:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            datos = documento.to_dict() or {}
            if datos.get("estado") == "Archivado":
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")
            actuales = list(datos.get("alergias", []))
            ya = {busqueda.normalizar(a["sustancia"]).strip() for a in actuales}
            if ya & {busqueda.normalizar(a.sustancia).strip() for a in alergias}:
                raise DatosInvalidos("Esa alergia ya estaba registrada.")
            transaccion.update(
                referencia,
                {
                    "alergias": actuales + [_sin_nulos(asdict(a)) for a in alergias],
                    "alergias_evaluadas": True,
                    "actualizado_en": firestore.SERVER_TIMESTAMP,
                },
            )

        agregar(self.unidad.cliente.transaction())

    def archivar(self, id_paciente: str, baja: Baja) -> None:
        referencia = self.referencia(id_paciente)
        if referencia is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")

        @firestore.transactional
        def archivar_si_activo(transaccion: Transaction) -> None:
            documento = referencia.get(transaction=transaccion)
            if not documento.exists:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if (documento.to_dict() or {}).get("estado") == "Archivado":
                raise PacienteArchivado("El historial ya estaba archivado.")
            transaccion.update(
                referencia,
                {
                    "estado": "Archivado",
                    "fecha_baja": baja.fecha,
                    "motivo_baja": baja.motivo.value,
                    "detalle_baja": baja.detalle,
                    "archivado_por": baja.id_profesional,
                    "actualizado_en": firestore.SERVER_TIMESTAMP,
                },
            )

        archivar_si_activo(self.unidad.cliente.transaction())


class RepositorioHistorialFirestore:
    def __init__(self, unidad: "UnidadTrabajoFirestore") -> None:
        self.unidad = unidad

    def _consultas(self, id_paciente: str):
        return (
            self.unidad.cliente.collection(COLECCION_PACIENTES)
            .document(id_paciente)
            .collection(SUBCOLECCION_CONSULTAS)
        )

    @staticmethod
    def _a_consulta(id_consulta: str, id_paciente: str, datos: dict[str, Any]) -> Consulta:
        return Consulta(
            id_consulta=id_consulta,
            id_paciente=id_paciente,
            id_profesional=datos["id_profesional_central"],
            fecha_hora=datos["fecha_hora"],
            motivo=datos["motivo"],
            notas=datos.get("notas"),
            diagnosticos=tuple(Diagnostico(**d) for d in datos.get("diagnosticos", [])),
            tratamientos=tuple(Tratamiento(**t) for t in datos.get("tratamientos", [])),
            recetas=tuple(Receta(**r) for r in datos.get("recetas", [])),
        )

    def listar_consultas(
        self, id_paciente: str, limite: int, antes_de: datetime | None = None
    ) -> list[Consulta]:
        if not _id_valido(id_paciente):
            return []
        consulta = self._consultas(id_paciente)
        if antes_de is not None:
            consulta = consulta.where(filter=FieldFilter("fecha_hora", "<", antes_de))
        consulta = consulta.order_by("fecha_hora", direction=firestore.Query.DESCENDING).limit(
            limite
        )
        return [
            self._a_consulta(d.id, id_paciente, d.to_dict())
            for d in consulta.stream(timeout=self.unidad.timeout)
        ]

    def obtener_consulta(self, id_paciente: str, id_consulta: str) -> Consulta | None:
        if not _id_valido(id_paciente) or not _id_valido(id_consulta):
            return None
        documento = (
            self._consultas(id_paciente).document(id_consulta).get(timeout=self.unidad.timeout)
        )
        if not documento.exists:
            return None
        return self._a_consulta(documento.id, id_paciente, documento.to_dict() or {})

    def agregar_a_consulta(
        self, id_paciente: str, id_consulta: str, id_profesional: str, adenda: Adenda
    ) -> Consulta:
        paciente = self.unidad.pacientes.referencia(id_paciente)
        if paciente is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if not _id_valido(id_consulta):
            raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")
        referencia = self._consultas(id_paciente).document(id_consulta)
        ahora = datetime.now(UTC)
        rotulo = adenda.rotular(ahora, id_profesional)

        @firestore.transactional
        def agregar(transaccion: Transaction) -> Consulta:
            # Un solo documento leido y reescrito en una transaccion: dos adendas
            # simultaneas se aplican una tras otra sin perderse.
            actual = paciente.get(transaction=transaccion)
            if not actual.exists:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if (actual.to_dict() or {}).get("estado") == "Archivado":
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")
            documento = referencia.get(transaction=transaccion)
            if not documento.exists:
                raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")
            previa = self._a_consulta(documento.id, id_paciente, documento.to_dict() or {})
            notas = f"{previa.notas}\n\n{rotulo}" if previa.notas else rotulo
            diagnosticos = previa.diagnosticos + adenda.diagnosticos
            tratamientos = previa.tratamientos + adenda.tratamientos
            recetas = previa.recetas + adenda.recetas
            transaccion.update(
                referencia,
                {
                    "notas": notas,
                    "diagnosticos": [_sin_nulos(asdict(d)) for d in diagnosticos],
                    "tratamientos": [_sin_nulos(asdict(t)) for t in tratamientos],
                    "recetas": [_sin_nulos(asdict(r)) for r in recetas],
                },
            )
            return Consulta(
                previa.id_consulta,
                id_paciente,
                previa.id_profesional,
                previa.fecha_hora,
                previa.motivo,
                notas,
                diagnosticos,
                tratamientos,
                recetas,
            )

        return agregar(self.unidad.cliente.transaction())

    def registrar_consulta(
        self, id_paciente: str, id_profesional: str, datos: NuevaConsulta
    ) -> Consulta:
        paciente = self.unidad.pacientes.referencia(id_paciente)
        if paciente is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        referencia = self._consultas(id_paciente).document()
        fecha_hora = datetime.now(UTC)
        documento = {
            "id_profesional_central": id_profesional,
            "fecha_hora": fecha_hora,
            "motivo": datos.motivo,
            "notas": datos.notas,
            # Embebidos: se registran juntos y son pocos. Un documento = una escritura atomica.
            "diagnosticos": [_sin_nulos(asdict(d)) for d in datos.diagnosticos],
            "tratamientos": [_sin_nulos(asdict(t)) for t in datos.tratamientos],
            "recetas": [_sin_nulos(asdict(r)) for r in datos.recetas],
            "creado_en": firestore.SERVER_TIMESTAMP,
        }

        @firestore.transactional
        def crear_si_activo(transaccion: Transaction) -> None:
            actual = paciente.get(transaction=transaccion)
            if not actual.exists:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if (actual.to_dict() or {}).get("estado") == "Archivado":
                raise PacienteArchivado("El historial esta archivado; no admite consultas nuevas.")
            transaccion.create(referencia, documento)

        crear_si_activo(self.unidad.cliente.transaction())
        return Consulta(
            referencia.id,
            id_paciente,
            id_profesional,
            fecha_hora,
            datos.motivo,
            datos.notas,
            datos.diagnosticos,
            datos.tratamientos,
            datos.recetas,
        )


class RepositorioProfesionalesFirestore:
    def __init__(self, unidad: "UnidadTrabajoFirestore") -> None:
        self.unidad = unidad

    def obtener(self, id_profesional: str) -> ProfesionalLocal | None:
        if not _id_valido(id_profesional):
            return None
        documento = (
            self.unidad.cliente.collection(COLECCION_PROFESIONALES)
            .document(id_profesional)
            .get(timeout=self.unidad.timeout)
        )
        if not documento.exists:
            return None
        datos = documento.to_dict() or {}
        return ProfesionalLocal(
            documento.id,
            datos.get("nombres", ""),
            datos.get("apellidos", ""),
            datos.get("rol", ""),
            bool(datos.get("activo", False)),
        )


class RepositorioCitasFirestore:
    def __init__(self, unidad: "UnidadTrabajoFirestore") -> None:
        self.unidad = unidad

    @property
    def _citas(self):
        return self.unidad.cliente.collection(COLECCION_CITAS)

    def _agenda(self, id_profesional: str, dia: date) -> DocumentReference:
        return self.unidad.cliente.collection(COLECCION_AGENDAS).document(
            f"{id_profesional}_{dia.isoformat()}"
        )

    def _dias(self, inicio: datetime, fin: datetime) -> list[date]:
        """Dias locales de la clinica que toca la cita (una cita puede cruzar medianoche)."""
        primero = inicio.astimezone(self.unidad.zona).date()
        ultimo = (fin - timedelta(microseconds=1)).astimezone(self.unidad.zona).date()
        return [primero + timedelta(days=n) for n in range((ultimo - primero).days + 1)]

    @staticmethod
    def _a_cita(id_cita: str, datos: dict[str, Any]) -> Cita:
        return Cita(
            id_cita=id_cita,
            id_paciente=datos["id_paciente"],
            nombre_paciente=datos.get("nombre_paciente", ""),
            id_profesional=datos["id_profesional"],
            inicio=datos["inicio"],
            fin=datos["fin"],
            motivo=datos.get("motivo", ""),
            estado=EstadoCita(datos["estado"]),
            creada_por=datos.get("creada_por", ""),
            motivo_cambio=datos.get("motivo_cambio"),
        )

    def obtener(self, id_cita: str) -> Cita | None:
        if not _id_valido(id_cita):
            return None
        documento = self._citas.document(id_cita).get(timeout=self.unidad.timeout)
        return self._a_cita(documento.id, documento.to_dict()) if documento.exists else None

    def agendar(self, datos: NuevaCita, nombre_paciente: str, creada_por: str) -> Cita:
        referencia = self._citas.document()
        inicio, fin = datos.inicio.astimezone(UTC), datos.fin.astimezone(UTC)
        agendas = [self._agenda(datos.id_profesional, dia) for dia in self._dias(inicio, fin)]
        paciente = self.unidad.pacientes.referencia(datos.id_paciente)
        if paciente is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")

        @firestore.transactional
        def reservar(transaccion: Transaction) -> None:
            # Leer los documentos de agenda dentro de la transaccion los "bloquea":
            # si otra secretaria reserva el mismo dia, Firestore repite esta funcion.
            actual = paciente.get(transaction=transaccion)
            if not actual.exists:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            if (actual.to_dict() or {}).get("estado") == "Archivado":
                raise PacienteArchivado("El historial esta archivado; no admite citas nuevas.")
            leidas = [agenda.get(transaction=transaccion) for agenda in agendas]
            for leida in leidas:
                ocupado = (leida.to_dict() or {}).get("ocupado", {}) if leida.exists else {}
                for intervalo in ocupado.values():
                    if intervalo["inicio"] < fin and inicio < intervalo["fin"]:
                        raise ConflictoAgenda("El profesional ya tiene una cita en ese horario.")
            transaccion.create(
                referencia,
                {
                    "id_paciente": datos.id_paciente,
                    "nombre_paciente": nombre_paciente,
                    "id_profesional": datos.id_profesional,
                    "inicio": inicio,
                    "fin": fin,
                    "duracion_minutos": datos.duracion_minutos,
                    "motivo": datos.motivo,
                    "estado": EstadoCita.PROGRAMADA.value,
                    "creada_por": creada_por,
                    "creada_en": firestore.SERVER_TIMESTAMP,
                },
            )
            for agenda in agendas:
                transaccion.set(
                    agenda,
                    {
                        "id_profesional": datos.id_profesional,
                        "ocupado": {referencia.id: {"inicio": inicio, "fin": fin}},
                    },
                    merge=True,
                )

        reservar(self.unidad.cliente.transaction())
        return Cita(
            referencia.id,
            datos.id_paciente,
            nombre_paciente,
            datos.id_profesional,
            inicio,
            fin,
            datos.motivo,
            EstadoCita.PROGRAMADA,
            creada_por,
        )

    def listar_agenda(
        self, desde: datetime, hasta: datetime, id_profesional: str | None = None
    ) -> list[Cita]:
        consulta = (
            self._citas.where(filter=FieldFilter("inicio", ">=", desde))
            .where(filter=FieldFilter("inicio", "<", hasta))
            .order_by("inicio")
            .limit(MAXIMO_AGENDA)
        )
        citas = [
            self._a_cita(d.id, d.to_dict()) for d in consulta.stream(timeout=self.unidad.timeout)
        ]
        # Filtrar el profesional aqui evita exigir un indice compuesto (profesional + inicio).
        if id_profesional is not None:
            citas = [c for c in citas if c.id_profesional == id_profesional]
        return citas

    def listar_por_paciente(self, id_paciente: str, limite: int) -> list[Cita]:
        # Igualdad sola usa el indice automatico; el orden se aplica aqui (pocas citas).
        consulta = self._citas.where(filter=FieldFilter("id_paciente", "==", id_paciente))
        citas = [
            self._a_cita(d.id, d.to_dict())
            for d in consulta.limit(MAXIMO_AGENDA).stream(timeout=self.unidad.timeout)
        ]
        return sorted(citas, key=lambda c: c.inicio, reverse=True)[:limite]

    def cambiar_estado(
        self, id_cita: str, estado: EstadoCita, por: str, motivo: str | None
    ) -> Cita:
        if not _id_valido(id_cita):
            raise CitaNoEncontrada("La cita no existe en tu institucion.")
        referencia = self._citas.document(id_cita)

        @firestore.transactional
        def cambiar(transaccion: Transaction) -> Cita:
            documento = referencia.get(transaction=transaccion)
            if not documento.exists:
                raise CitaNoEncontrada("La cita no existe en tu institucion.")
            actual = self._a_cita(documento.id, documento.to_dict())
            if estado not in TRANSICIONES.get(actual.estado, set()):
                raise ConflictoAgenda(f"Una cita '{actual.estado}' no puede pasar a '{estado}'.")
            transaccion.update(
                referencia,
                {
                    "estado": estado.value,
                    "motivo_cambio": motivo,
                    "actualizada_por": por,
                    "actualizada_en": firestore.SERVER_TIMESTAMP,
                },
            )
            if estado not in ESTADOS_OCUPAN_HORARIO:
                # Cancelada, atendida o no asistio: liberar el horario en cada dia que ocupaba.
                for dia in self._dias(actual.inicio, actual.fin):
                    transaccion.update(
                        self._agenda(actual.id_profesional, dia),
                        {f"ocupado.`{id_cita}`": firestore.DELETE_FIELD},
                    )
            return Cita(
                actual.id_cita,
                actual.id_paciente,
                actual.nombre_paciente,
                actual.id_profesional,
                actual.inicio,
                actual.fin,
                actual.motivo,
                estado,
                actual.creada_por,
                motivo,
            )

        return cambiar(self.unidad.cliente.transaction())


class RepositorioOdontogramaFirestore:
    def __init__(self, unidad: "UnidadTrabajoFirestore") -> None:
        self.unidad = unidad

    def _referencia(self, id_paciente: str) -> DocumentReference:
        return (
            self.unidad.cliente.collection(COLECCION_PACIENTES)
            .document(id_paciente)
            .collection("odontograma")
            .document("actual")
        )

    def obtener(self, id_paciente: str) -> Odontograma:
        documento = self._referencia(id_paciente).get(timeout=self.unidad.timeout)
        piezas = (documento.to_dict() or {}).get("piezas", {}) if documento.exists else {}
        return Odontograma(
            id_paciente,
            {
                codigo: EstadoPieza(
                    pieza=codigo,
                    estado=EstadoDental(datos["estado"]),
                    actualizado_por=datos.get("actualizado_por", ""),
                    actualizado_en=datos["actualizado_en"],
                    superficies=tuple(Superficie(s) for s in datos.get("superficies", [])),
                    nota=datos.get("nota"),
                )
                for codigo, datos in sorted(piezas.items())
            },
        )

    def actualizar_pieza(self, id_paciente: str, estado: EstadoPieza) -> None:
        # Documento aparte del paciente: datos clinicos restringidos que la secretaria
        # no necesita; acotado a 52 piezas, cabe holgado en 1 MiB.
        self.unidad.lote.set(
            self._referencia(id_paciente),
            {
                "piezas": {
                    estado.pieza: {
                        "estado": estado.estado.value,
                        "superficies": [s.value for s in estado.superficies],
                        "nota": estado.nota,
                        "actualizado_por": estado.actualizado_por,
                        "actualizado_en": estado.actualizado_en,
                    }
                },
                "actualizado_en": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )


class UnidadTrabajoFirestore:
    """Una por solicitud. Comparte el cliente (thread-safe) y crea su propio batch."""

    def __init__(
        self,
        cliente: Client,
        zona: ZoneInfo | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.cliente = cliente
        self.zona = zona or ZoneInfo("America/Guatemala")
        self.timeout = timeout
        self.lote: WriteBatch = cliente.batch()
        self.pacientes = RepositorioPacientesFirestore(self)
        self.historial = RepositorioHistorialFirestore(self)
        self.profesionales = RepositorioProfesionalesFirestore(self)
        self.citas = RepositorioCitasFirestore(self)
        self.odontograma = RepositorioOdontogramaFirestore(self)
        # Crecimiento y vacunacion son del Centro Pediatrico: aqui responden 501.
        pendientes = repositorios_pendientes(MOTOR)
        self.crecimiento = pendientes["crecimiento"]
        self.vacunacion = pendientes["vacunacion"]
        self.laboratorio = pendientes["laboratorio"]

    def __enter__(self) -> Self:
        self.lote = self.cliente.batch()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        self.rollback()
        if isinstance(exc_value, ERRORES_FIRESTORE):
            # El detalle queda en la consola del servidor, no en la respuesta HTTP.
            logger.warning("Firestore no disponible: %s", exc_value)
            raise IntegracionNoConfigurada(
                "La base de la clinica odontologica no esta disponible."
            ) from exc_value
        return False

    def commit(self) -> None:
        if len(self.lote):
            self.lote.commit(timeout=self.timeout)
        self.lote = self.cliente.batch()

    def rollback(self) -> None:
        # Un batch sin confirmar no envio nada: descartarlo equivale a revertir.
        self.lote = self.cliente.batch()
