"""Laboratorio Clinico (MongoDB): registrar paciente, historial, consultas, archivo y busqueda.

MongoDB se ejecuta como servidor unico (sin conjunto de replicas), por lo que NO hay
transacciones entre documentos. El adaptador conserva el contrato comun asi:

- Las escrituras se acumulan en la unidad y se ejecutan en commit(); sin commit() no se
  guarda nada (igual que en los motores SQL).
- Cada operacion de negocio escribe un solo documento: un paciente nuevo, una consulta
  con todos sus diagnosticos/tratamientos/recetas embebidos (atomica por ser un documento)
  o el cambio de estado de un paciente (UPDATE condicional atomico).
- Consulta vs. baja concurrentes: antes de insertar la consulta se hace una escritura
  condicional sobre el paciente (`estado: Activo`). Es el punto de serializacion con la
  baja. Una consulta aceptada justo antes de la baja puede terminar de escribirse unos
  milisegundos despues; queda en el historial con fecha anterior a la baja. Con un
  conjunto de replicas se podria usar una transaccion y eliminar esa ventana.
"""

import re
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, time
from types import TracebackType
from typing import Any, Literal, Self
from uuid import UUID, uuid4

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.collation import Collation
from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError, WriteError

from app.application.errores import IntegracionNoConfigurada
from app.domain.busqueda import normalizar
from app.domain.cita import TRANSICIONES, Cita, EstadoCita, NuevaCita
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
    ConflictoEstado,
    ConsultaNoEncontrada,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
    RegistroNoEncontrado,
)
from app.domain.laboratorio import (
    ESTADOS_ABIERTOS,
    EstadoOrden,
    Muestra,
    NuevaMuestra,
    Orden,
    ParametroPrueba,
    PruebaCatalogo,
    PruebaOrden,
    Referencia,
    Resultado,
    TipoValor,
)
from app.domain.paciente import (
    Alergia,
    Baja,
    CambiosPaciente,
    Contacto,
    NuevoPaciente,
    Paciente,
)
from app.domain.profesional import ProfesionalLocal
from app.infrastructure.persistence.comun import con_utc
from app.infrastructure.persistence.pendiente import repositorios_pendientes

MOTOR = "MongoDB"
ESTADO_ACTIVO = "Activo"
ESTADO_ARCHIVADO = "Archivado"
VALIDACION_DOCUMENTO = 121  # el documento no cumple el $jsonSchema de la coleccion
ORDEN_NOMBRE = Collation(locale="es", strength=1)  # sin mayusculas ni acentos

ESTADO_ORDEN_BD = {
    EstadoOrden.SOLICITADA: "Solicitada",
    EstadoOrden.EN_PROCESO: "En proceso",
    EstadoOrden.VALIDADA: "Validada",
    EstadoOrden.CANCELADA: "Cancelada",
}
ESTADO_ORDEN_DOMINIO = {texto: estado for estado, texto in ESTADO_ORDEN_BD.items()}
ABIERTAS_BD = [ESTADO_ORDEN_BD[e] for e in ESTADOS_ABIERTOS]

ESTADO_CITA_BD = {
    EstadoCita.PROGRAMADA: "Programada",
    EstadoCita.CONFIRMADA: "Confirmada",
    EstadoCita.ATENDIDA: "Atendida",
    EstadoCita.CANCELADA: "Cancelada",
    EstadoCita.NO_ASISTIO: "No asistio",
}
ESTADO_CITA_DOMINIO = {texto: estado for estado, texto in ESTADO_CITA_BD.items()}
OCUPAN_HORARIO = {EstadoCita.PROGRAMADA, EstadoCita.CONFIRMADA}


def _limpio(valor: str | None) -> str | None:
    """El validador del laboratorio exige texto con algun caracter visible: se omite el vacio."""
    if valor is None or not valor.strip():
        return None
    return valor


def _sin_vacios(datos: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in datos.items() if v is not None}


def _a_fecha_bson(valor: date) -> datetime:
    return datetime.combine(valor, time.min, tzinfo=UTC)


def _milisegundos(valor: datetime) -> datetime:
    """MongoDB guarda fechas con precision de milisegundo: se devuelve lo que se guarda."""
    return valor.replace(microsecond=valor.microsecond // 1000 * 1000)


def _contacto(valor: dict | None) -> Contacto | None:
    if not valor:
        return None
    return Contacto(valor.get("telefono"), valor.get("correo"), valor.get("direccion"))


def _alergias(row: dict) -> tuple[Alergia, ...]:
    return tuple(
        Alergia(a["sustancia"], a.get("reaccion"), a.get("severidad"))
        for a in row.get("alergias", [])
    )


def _identificador(texto: str) -> ObjectId | None:
    try:
        return ObjectId(texto) if len(texto) == 24 else None
    except (InvalidId, TypeError):
        return None


def _clases_de_letras() -> dict[str, str]:
    """Para cada letra base, todas las letras Latinas que se reducen a ella ("e": eEéÉèÈêë...)."""
    grupos: dict[str, set[str]] = {}
    for punto in [*range(0x41, 0x5B), *range(0x61, 0x7B), *range(0xC0, 0x250)]:
        letra = chr(punto)
        base = normalizar(letra)
        if len(base) == 1 and base.isalpha():
            grupos.setdefault(base, set()).update({letra, letra.lower(), letra.upper()})
    return {base: "".join(sorted(letras)) for base, letras in grupos.items()}


_CLASES = _clases_de_letras()


def _patron_palabra(palabra: str) -> str:
    """Regex "comienza una palabra con ...", insensible a mayusculas y acentos.

    MongoDB no ignora acentos en $regex (ni siquiera con colacion), asi que cada letra
    se sustituye por la clase de sus variantes. Las demas se escapan como texto literal.
    """
    partes = []
    for caracter in normalizar(palabra):
        clase = _CLASES.get(caracter)
        partes.append(f"[{re.escape(clase)}]" if clase else re.escape(caracter))
    return r"(^|\s)" + "".join(partes)


def _a_consulta(row: dict, id_paciente: str) -> Consulta:
    return Consulta(
        str(row["_id"]),
        id_paciente,
        row["id_profesional_central"],
        con_utc(row["fecha_hora"]),
        row["motivo"],
        row.get("notas"),
        tuple(
            Diagnostico(d["descripcion"], d.get("codigo"), d.get("sistema_codigo"))
            for d in row.get("diagnosticos", [])
        ),
        tuple(Tratamiento(t["descripcion"]) for t in row.get("tratamientos", [])),
        tuple(
            Receta(
                r["medicamento"],
                r["dosis"],
                r["frecuencia"],
                r.get("via_administracion"),
                r.get("duracion_dias"),
                r.get("instrucciones"),
            )
            for r in row.get("recetas", [])
        ),
    )


def _doc_diagnostico(d: Diagnostico) -> dict[str, Any]:
    return _sin_vacios(
        {
            "descripcion": d.descripcion,
            "codigo": _limpio(d.codigo),
            "sistema_codigo": _limpio(d.sistema_codigo),
        }
    )


def _doc_receta(r: Receta) -> dict[str, Any]:
    return _sin_vacios(
        {
            "medicamento": r.medicamento,
            "dosis": r.dosis,
            "frecuencia": r.frecuencia,
            "via_administracion": _limpio(r.via_administracion),
            "duracion_dias": r.duracion_dias,
            "instrucciones": _limpio(r.instrucciones),
        }
    )


def _doc_alergia(a: Alergia) -> dict[str, Any]:
    return _sin_vacios(
        {
            "sustancia": a.sustancia,
            "reaccion": _limpio(a.reaccion),
            "severidad": _limpio(a.severidad),
        }
    )


class RepositorioPacientesMongo:
    def __init__(self, unidad: "UnidadTrabajoMongo") -> None:
        self.unidad = unidad
        self.coleccion = unidad.database.pacientes

    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        identificador = _identificador(id_paciente)
        if identificador is None:
            return None
        row = self.coleccion.find_one(
            {"_id": identificador},
            {
                "nombres": 1,
                "apellidos": 1,
                "fecha_nacimiento": 1,
                "estado": 1,
                "contacto": 1,
                "alergias_evaluadas": 1,
                "alergias": 1,
            },
        )
        if row is None:
            return None
        fecha = row.get("fecha_nacimiento")
        return Paciente(
            str(row["_id"]),
            row["nombres"],
            row["apellidos"],
            fecha.date() if fecha else None,
            archivado=row.get("estado") == ESTADO_ARCHIVADO,
            contacto=_contacto(row.get("contacto")),
            alergias=_alergias(row) if row.get("alergias_evaluadas") else None,
        )

    def registrar(self, datos: NuevoPaciente) -> Paciente:
        identificador = ObjectId()
        ahora = datetime.now(UTC)
        contacto = _sin_vacios(
            {
                "telefono": _limpio(datos.contacto.telefono) if datos.contacto else None,
                "correo": _limpio(datos.contacto.correo) if datos.contacto else None,
                "direccion": _limpio(datos.contacto.direccion) if datos.contacto else None,
            }
        )
        documento: dict[str, Any] = {
            "_id": identificador,
            "nombres": datos.nombres,
            "apellidos": datos.apellidos,
            "estado": ESTADO_ACTIVO,
            "creado_en": ahora,
            "actualizado_en": ahora,
        }
        if datos.fecha_nacimiento is not None:
            documento["fecha_nacimiento"] = _a_fecha_bson(datos.fecha_nacimiento)
        if contacto:
            documento["contacto"] = contacto
        if datos.alergias is not None:
            documento["alergias_evaluadas"] = True
            documento["alergias"] = [_doc_alergia(a) for a in datos.alergias]

        def insertar() -> None:
            # El numero de expediente es unico: ante la colision (practicamente imposible)
            # se genera otro.
            for _ in range(3):
                documento["numero_expediente"] = "LAB-" + uuid4().hex[:20].upper()
                try:
                    self.coleccion.insert_one(documento)
                    return
                except DuplicateKeyError as error:
                    if "numero_expediente" not in str(error):
                        raise
            raise IntegracionNoConfigurada("No se pudo asignar un numero de expediente.")

        self.unidad.pendientes.append(insertar)
        return Paciente(
            str(identificador),
            datos.nombres,
            datos.apellidos,
            datos.fecha_nacimiento,
            contacto=datos.contacto,
            alergias=datos.alergias,
        )

    def _estado(self, id_paciente: str) -> ObjectId:
        identificador = _identificador(id_paciente)
        fila = (
            self.coleccion.find_one({"_id": identificador}, {"estado": 1})
            if identificador
            else None
        )
        if fila is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if fila.get("estado") == ESTADO_ARCHIVADO:
            raise PacienteArchivado("El historial esta archivado; no admite cambios.")
        return identificador

    def actualizar(self, id_paciente: str, cambios: CambiosPaciente) -> None:
        identificador = self._estado(id_paciente)
        poner: dict[str, Any] = {"actualizado_en": datetime.now(UTC)}
        quitar: dict[str, str] = {}
        if cambios.nombres is not None:
            poner["nombres"] = cambios.nombres
        if cambios.apellidos is not None:
            poner["apellidos"] = cambios.apellidos
        if cambios.fecha_nacimiento is not None:
            if cambios.fecha_nacimiento > date.today():
                raise DatosInvalidos("La fecha de nacimiento no puede ser futura.")
            poner["fecha_nacimiento"] = _a_fecha_bson(cambios.fecha_nacimiento)
        if cambios.contacto is not None:  # reemplaza el contacto completo
            contacto = _sin_vacios(
                {
                    "telefono": _limpio(cambios.contacto.telefono),
                    "correo": _limpio(cambios.contacto.correo),
                    "direccion": _limpio(cambios.contacto.direccion),
                }
            )
            if contacto:
                poner["contacto"] = contacto
            else:
                quitar["contacto"] = ""
        operacion: dict[str, Any] = {"$set": poner}
        if quitar:
            operacion["$unset"] = quitar

        def escribir() -> None:
            resultado = self.coleccion.update_one(
                {"_id": identificador, "estado": ESTADO_ACTIVO}, operacion
            )
            if resultado.matched_count == 0:
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")

        self.unidad.pendientes.append(escribir)

    def agregar_alergias(self, id_paciente: str, alergias: tuple[Alergia, ...]) -> None:
        identificador = self._estado(id_paciente)
        actuales = self.coleccion.find_one({"_id": identificador}, {"alergias": 1}) or {}
        existentes = {normalizar(a["sustancia"]).strip() for a in actuales.get("alergias", [])}
        if existentes & {normalizar(a.sustancia).strip() for a in alergias}:
            raise DatosInvalidos("Esa alergia ya estaba registrada.")
        nuevas = [_doc_alergia(a) for a in alergias]

        def escribir() -> None:
            resultado = self.coleccion.update_one(
                {"_id": identificador, "estado": ESTADO_ACTIVO},
                {
                    "$push": {"alergias": {"$each": nuevas}},
                    "$set": {"alergias_evaluadas": True, "actualizado_en": datetime.now(UTC)},
                },
            )
            if resultado.matched_count == 0:
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")

        self.unidad.pendientes.append(escribir)

    def buscar(self, palabras: tuple[str, ...], limite: int) -> list[Paciente]:
        # Regla comun (domain/busqueda.py): cada palabra es el comienzo de alguna palabra del
        # nombre. Una palabra no puede cruzar nombres y apellidos, asi que basta buscarla en
        # cualquiera de los dos campos.
        condiciones = []
        for palabra in palabras:
            patron = _patron_palabra(palabra)
            condiciones.append(
                {"$or": [{"nombres": {"$regex": patron}}, {"apellidos": {"$regex": patron}}]}
            )
        cursor = (
            self.coleccion.find(
                {"$and": condiciones},
                {"nombres": 1, "apellidos": 1, "fecha_nacimiento": 1, "estado": 1},
            )
            .collation(ORDEN_NOMBRE)
            .sort([("apellidos", 1), ("nombres", 1), ("_id", 1)])
            .limit(limite)
        )
        return [
            Paciente(
                str(row["_id"]),
                row["nombres"],
                row["apellidos"],
                row["fecha_nacimiento"].date() if row.get("fecha_nacimiento") else None,
                archivado=row.get("estado") == ESTADO_ARCHIVADO,
            )
            for row in cursor
        ]

    def archivar(self, id_paciente: str, baja: Baja) -> None:
        identificador = _identificador(id_paciente)
        if identificador is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        try:
            quien = str(UUID(baja.id_profesional))
        except ValueError as error:
            raise ProfesionalNoVinculado("La cuenta no es valida para dar de baja.") from error
        estado = self.coleccion.find_one({"_id": identificador}, {"estado": 1})
        if estado is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if estado.get("estado") == ESTADO_ARCHIVADO:
            raise PacienteArchivado("El historial ya estaba archivado.")
        cambios = _sin_vacios(
            {
                "estado": ESTADO_ARCHIVADO,
                "fecha_baja": _milisegundos(con_utc(baja.fecha)),
                "motivo_baja": baja.motivo.value,
                "detalle_baja": _limpio(baja.detalle),
                "archivado_por": quien,
                "actualizado_en": datetime.now(UTC),
            }
        )

        def actualizar() -> None:
            # Condicional y atomico: si otra solicitud lo archivo primero, no se sobrescribe.
            resultado = self.coleccion.update_one(
                {"_id": identificador, "estado": ESTADO_ACTIVO}, {"$set": cambios}
            )
            if resultado.matched_count == 0:
                raise PacienteArchivado("El historial ya estaba archivado.")

        self.unidad.pendientes.append(actualizar)


class RepositorioHistorialMongo:
    def __init__(self, unidad: "UnidadTrabajoMongo") -> None:
        self.unidad = unidad
        self.database = unidad.database

    def _comprobar_profesional(self, id_profesional: str) -> str:
        try:
            uuid = str(UUID(id_profesional))
        except ValueError as error:
            raise ProfesionalNoVinculado(
                "Tu cuenta no es un profesional de este laboratorio."
            ) from error
        activo = self.database.profesionales.find_one(
            {"id_profesional_central": uuid, "activo": True}, {"_id": 1}
        )
        if activo is None:
            raise ProfesionalNoVinculado(
                "Tu cuenta no esta vinculada a personal activo del Laboratorio Clinico. "
                "Pide que ejecuten: python -m scripts.sincronizar_profesionales"
            )
        return uuid

    def registrar_consulta(
        self, id_paciente: str, id_profesional: str, datos: NuevaConsulta
    ) -> Consulta:
        identificador = _identificador(id_paciente)
        if identificador is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        uuid = self._comprobar_profesional(id_profesional)
        estado = self.database.pacientes.find_one({"_id": identificador}, {"estado": 1})
        if estado is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if estado.get("estado") == ESTADO_ARCHIVADO:
            raise PacienteArchivado("El historial esta archivado; no admite consultas nuevas.")

        ahora = _milisegundos(datetime.now(UTC))
        id_consulta = ObjectId()
        documento: dict[str, Any] = {
            "_id": id_consulta,
            "id_paciente": identificador,
            "id_profesional_central": uuid,
            "fecha_hora": ahora,
            "motivo": datos.motivo,
            "diagnosticos": [_doc_diagnostico(d) for d in datos.diagnosticos],
            "tratamientos": [{"descripcion": t.descripcion} for t in datos.tratamientos],
            "recetas": [_doc_receta(r) for r in datos.recetas],
        }
        if _limpio(datos.notas):
            documento["notas"] = datos.notas

        def insertar() -> None:
            # Punto de serializacion con la baja (ver la nota del modulo).
            guarda = self.database.pacientes.update_one(
                {"_id": identificador, "estado": ESTADO_ACTIVO},
                {"$set": {"ultima_consulta_en": ahora, "actualizado_en": ahora}},
            )
            if guarda.matched_count == 0:
                raise PacienteArchivado("El historial esta archivado; no admite consultas nuevas.")
            self.database.consultas.insert_one(documento)

        self.unidad.pendientes.append(insertar)
        return Consulta(
            str(id_consulta),
            id_paciente,
            id_profesional,
            ahora,
            datos.motivo,
            datos.notas,
            datos.diagnosticos,
            datos.tratamientos,
            datos.recetas,
        )

    def listar_consultas(
        self, id_paciente: str, limite: int, antes_de: datetime | None = None
    ) -> list[Consulta]:
        identificador = _identificador(id_paciente)
        if identificador is None:
            return []
        filtro: dict[str, Any] = {"id_paciente": identificador}
        if antes_de is not None:
            filtro["fecha_hora"] = {"$lt": _milisegundos(con_utc(antes_de))}
        cursor = (
            self.database.consultas.find(filtro)
            .sort([("fecha_hora", -1), ("_id", -1)])
            .limit(limite)
        )
        return [_a_consulta(row, id_paciente) for row in cursor]

    def obtener_consulta(self, id_paciente: str, id_consulta: str) -> Consulta | None:
        paciente, consulta = _identificador(id_paciente), _identificador(id_consulta)
        if paciente is None or consulta is None:
            return None
        row = self.database.consultas.find_one({"_id": consulta, "id_paciente": paciente})
        return _a_consulta(row, id_paciente) if row else None

    def agregar_a_consulta(
        self, id_paciente: str, id_consulta: str, id_profesional: str, adenda: Adenda
    ) -> Consulta:
        paciente = _identificador(id_paciente)
        if paciente is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        consulta = _identificador(id_consulta)
        if consulta is None:
            raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")
        uuid = self._comprobar_profesional(id_profesional)
        estado = self.database.pacientes.find_one({"_id": paciente}, {"estado": 1})
        if estado is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if estado.get("estado") == ESTADO_ARCHIVADO:
            raise PacienteArchivado("El historial esta archivado; no admite cambios.")
        actual = self.database.consultas.find_one({"_id": consulta, "id_paciente": paciente})
        if actual is None:
            raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")

        ahora = _milisegundos(datetime.now(UTC))
        rotulo = adenda.rotular(ahora, uuid)
        diagnosticos = [_doc_diagnostico(d) for d in adenda.diagnosticos]
        tratamientos = [{"descripcion": t.descripcion} for t in adenda.tratamientos]
        recetas = [_doc_receta(r) for r in adenda.recetas]

        def concatenar(campo: str, nuevos: list[dict[str, Any]]) -> dict[str, Any]:
            # $literal: el texto de la adenda nunca se interpreta como expresion ni "$campo".
            return {"$concatArrays": [{"$ifNull": [f"${campo}", []]}, {"$literal": nuevos}]}

        previas = {"$ifNull": ["$notas", ""]}
        pipeline = [
            {
                "$set": {
                    "diagnosticos": concatenar("diagnosticos", diagnosticos),
                    "tratamientos": concatenar("tratamientos", tratamientos),
                    "recetas": concatenar("recetas", recetas),
                    "notas": {
                        "$cond": [
                            {"$gt": [{"$strLenCP": previas}, 0]},
                            {"$concat": [previas, "\n\n", {"$literal": rotulo}]},
                            {"$literal": rotulo},
                        ]
                    },
                }
            }
        ]

        def escribir() -> None:
            # Punto de serializacion con la baja; despues, UNA actualizacion atomica del
            # documento: dos adendas simultaneas se aplican una tras otra sin perderse.
            guarda = self.database.pacientes.update_one(
                {"_id": paciente, "estado": ESTADO_ACTIVO},
                {"$set": {"actualizado_en": ahora}},
            )
            if guarda.matched_count == 0:
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")
            self.database.consultas.update_one({"_id": consulta, "id_paciente": paciente}, pipeline)

        self.unidad.pendientes.append(escribir)
        previo = _a_consulta(actual, id_paciente)
        notas = f"{previo.notas}\n\n{rotulo}" if previo.notas else rotulo
        return Consulta(
            previo.id_consulta,
            id_paciente,
            previo.id_profesional,
            previo.fecha_hora,
            previo.motivo,
            notas,
            previo.diagnosticos + adenda.diagnosticos,
            previo.tratamientos + adenda.tratamientos,
            previo.recetas + adenda.recetas,
        )


class RepositorioProfesionalesMongo:
    def __init__(self, unidad: "UnidadTrabajoMongo") -> None:
        self.unidad = unidad
        self.coleccion = unidad.database.profesionales

    def obtener(self, id_profesional: str) -> ProfesionalLocal | None:
        try:
            uuid = str(UUID(id_profesional))
        except ValueError:
            return None
        fila = self.coleccion.find_one({"id_profesional_central": uuid})
        if fila is None:
            return None
        return ProfesionalLocal(
            uuid,
            fila["nombres"],
            fila["apellidos"],
            str(fila.get("rol") or "medico").lower(),
            bool(fila["activo"]),
        )

    def sincronizar(self, perfil: ProfesionalLocal) -> None:
        uuid = str(UUID(perfil.id_profesional))
        cambios = {
            "nombres": perfil.nombres,
            "apellidos": perfil.apellidos,
            "rol": perfil.rol,
            "activo": perfil.activo,
        }
        coleccion = self.coleccion
        self.unidad.pendientes.append(
            lambda: coleccion.update_one(
                {"id_profesional_central": uuid}, {"$set": cambios}, upsert=True
            )
        )


def _minutos(inicio: datetime, fin: datetime) -> list[int]:
    """Minutos (desde la epoca) que ocupa [inicio, fin). La agenda tiene granularidad de 1 min."""
    primero = int(con_utc(inicio).timestamp() // 60)
    ultimo = -int(-con_utc(fin).timestamp() // 60)  # techo
    return list(range(primero, ultimo))


class RepositorioCitasMongo:
    """Citas del laboratorio (toma de muestras). El indice unico de `bloques` impide choques.

    Cada cita guarda un bloque por minuto ocupado ("<profesional>|<minuto>"). Un indice
    unico parcial (solo citas que ocupan horario) hace que MongoDB rechace atomicamente
    una cita que se cruza con otra: es el equivalente a la restriccion de exclusion de
    PostgreSQL. Cancelar la cita la saca del indice (ocupa = false).
    """

    def __init__(self, unidad: "UnidadTrabajoMongo") -> None:
        self.unidad = unidad
        self.coleccion = unidad.database.citas

    @staticmethod
    def _a_cita(row: dict) -> Cita:
        return Cita(
            id_cita=str(row["_id"]),
            id_paciente=str(row["id_paciente"]),
            nombre_paciente=row["nombre_paciente"],
            id_profesional=row["id_profesional_central"],
            inicio=con_utc(row["inicio"]),
            fin=con_utc(row["fin"]),
            motivo=row.get("motivo", ""),
            estado=ESTADO_CITA_DOMINIO[row["estado"]],
            creada_por=row.get("creada_por", ""),
            motivo_cambio=row.get("motivo_cambio"),
        )

    def obtener(self, id_cita: str) -> Cita | None:
        identificador = _identificador(id_cita)
        if identificador is None:
            return None
        row = self.coleccion.find_one({"_id": identificador})
        return self._a_cita(row) if row else None

    def agendar(self, datos: NuevaCita, nombre_paciente: str, creada_por: str) -> Cita:
        paciente = _identificador(datos.id_paciente)
        estado = (
            self.unidad.database.pacientes.find_one({"_id": paciente}, {"estado": 1})
            if paciente
            else None
        )
        if estado is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if estado.get("estado") == ESTADO_ARCHIVADO:
            raise PacienteArchivado("El historial esta archivado; no admite citas nuevas.")
        try:
            profesional, quien = str(UUID(datos.id_profesional)), str(UUID(creada_por))
        except ValueError as error:
            raise ProfesionalNoVinculado("La cuenta o el profesional no son validos.") from error
        activo = self.unidad.database.profesionales.find_one(
            {"id_profesional_central": profesional, "activo": True}, {"_id": 1}
        )
        if activo is None:
            raise DatosInvalidos("El profesional no existe, no esta activo o no atiende.")

        inicio = _milisegundos(con_utc(datos.inicio))
        fin = _milisegundos(con_utc(datos.fin))
        identificador = ObjectId()
        documento = {
            "_id": identificador,
            "id_paciente": paciente,
            "nombre_paciente": nombre_paciente,
            "id_profesional_central": profesional,
            "inicio": inicio,
            "fin": fin,
            "duracion_minutos": datos.duracion_minutos,
            "motivo": datos.motivo,
            "estado": ESTADO_CITA_BD[EstadoCita.PROGRAMADA],
            "ocupa": True,
            "bloques": [f"{profesional}|{m}" for m in _minutos(inicio, fin)],
            "creada_por": quien,
            "creada_en": _milisegundos(datetime.now(UTC)),
        }

        def insertar() -> None:
            try:
                self.coleccion.insert_one(documento)
            except DuplicateKeyError as error:
                raise ConflictoAgenda("El profesional ya tiene una cita en ese horario.") from error

        self.unidad.pendientes.append(insertar)
        return Cita(
            str(identificador),
            datos.id_paciente,
            nombre_paciente,
            profesional,
            inicio,
            fin,
            datos.motivo,
            EstadoCita.PROGRAMADA,
            quien,
        )

    def listar_agenda(
        self, desde: datetime, hasta: datetime, id_profesional: str | None = None
    ) -> list[Cita]:
        filtro: dict[str, Any] = {
            "inicio": {"$gte": _milisegundos(con_utc(desde)), "$lt": _milisegundos(con_utc(hasta))}
        }
        if id_profesional is not None:
            try:
                filtro["id_profesional_central"] = str(UUID(id_profesional))
            except ValueError:
                return []
        cursor = self.coleccion.find(filtro).sort([("inicio", 1), ("_id", 1)]).limit(500)
        return [self._a_cita(row) for row in cursor]

    def listar_por_paciente(self, id_paciente: str, limite: int) -> list[Cita]:
        identificador = _identificador(id_paciente)
        if identificador is None:
            return []
        cursor = (
            self.coleccion.find({"id_paciente": identificador})
            .sort([("inicio", -1), ("_id", -1)])
            .limit(limite)
        )
        return [self._a_cita(row) for row in cursor]

    def cambiar_estado(
        self, id_cita: str, estado: EstadoCita, por: str, motivo: str | None
    ) -> Cita:
        identificador = _identificador(id_cita)
        row = self.coleccion.find_one({"_id": identificador}) if identificador else None
        if row is None:
            raise CitaNoEncontrada("La cita no existe en tu institucion.")
        try:
            quien = str(UUID(por))
        except ValueError as error:
            raise ProfesionalNoVinculado("La cuenta no es valida.") from error
        actual = ESTADO_CITA_DOMINIO[row["estado"]]
        if estado not in TRANSICIONES.get(actual, set()):
            raise ConflictoAgenda(f"Una cita '{actual}' no puede pasar a '{estado}'.")
        cambios = _sin_vacios(
            {
                "estado": ESTADO_CITA_BD[estado],
                "ocupa": estado in OCUPAN_HORARIO,
                "motivo_cambio": motivo,
                "actualizada_por": quien,
                "actualizada_en": datetime.now(UTC),
            }
        )

        def escribir() -> None:
            # Condicional al estado leido: dos cambios simultaneos no se pisan.
            resultado = self.coleccion.update_one(
                {"_id": identificador, "estado": row["estado"]}, {"$set": cambios}
            )
            if resultado.matched_count == 0:
                raise ConflictoAgenda("La cita cambio de estado mientras se procesaba.")

        self.unidad.pendientes.append(escribir)
        return Cita(
            str(identificador),
            str(row["id_paciente"]),
            row["nombre_paciente"],
            row["id_profesional_central"],
            con_utc(row["inicio"]),
            con_utc(row["fin"]),
            row.get("motivo", ""),
            estado,
            row.get("creada_por", ""),
            motivo,
        )


def _doc_referencia(r: Referencia | None) -> dict[str, Any] | None:
    if r is None:
        return None
    doc = _sin_vacios(
        {
            "minimo": r.minimo,
            "maximo": r.maximo,
            "descripcion": _limpio(r.descripcion),
            "poblacion": _limpio(r.poblacion),
        }
    )
    return doc or None


def _referencia(doc: dict | None) -> Referencia | None:
    if not doc:
        return None
    return Referencia(
        doc.get("minimo"), doc.get("maximo"), doc.get("descripcion"), doc.get("poblacion")
    )


def _doc_parametro(p: ParametroPrueba) -> dict[str, Any]:
    return _sin_vacios(
        {
            "codigo": p.codigo,
            "nombre": p.nombre,
            "unidad": _limpio(p.unidad),
            "tipo_valor": p.tipo_valor.value,
            "referencia": _doc_referencia(p.referencia),
        }
    )


def _parametro(doc: dict) -> ParametroPrueba:
    return ParametroPrueba(
        doc["codigo"],
        doc["nombre"],
        TipoValor(doc["tipo_valor"]),
        doc.get("unidad"),
        _referencia(doc.get("referencia")),
    )


def _doc_resultado(r: Resultado) -> dict[str, Any]:
    return _sin_vacios(
        {
            "codigo": r.codigo,
            "nombre": r.nombre,
            "unidad": _limpio(r.unidad),
            "tipo_valor": r.tipo_valor.value,
            "valor": r.valor,
            "referencia": _doc_referencia(r.referencia),
            "interpretacion": r.interpretacion,
        }
    )


def _resultado(doc: dict) -> Resultado:
    return Resultado(
        doc["codigo"],
        doc["nombre"],
        TipoValor(doc["tipo_valor"]),
        doc["valor"],
        doc.get("unidad"),
        _referencia(doc.get("referencia")),
        doc.get("interpretacion"),
    )


class RepositorioLaboratorioMongo:
    """Ordenes de laboratorio. Cada orden es UN documento con copia de las pruebas.

    Las modificaciones son actualizaciones condicionales al estado de la orden
    (solicitada / en proceso): asi una validacion y un cambio de resultados simultaneos no se
    pisan, y una orden validada o cancelada no vuelve a cambiar (ademas, el validador de la
    coleccion exige resultados en todas las pruebas de una orden validada).
    """

    def __init__(self, unidad: "UnidadTrabajoMongo") -> None:
        self.unidad = unidad
        self.coleccion = unidad.database.ordenes_laboratorio

    # --- lectura -------------------------------------------------------------------------

    def listar_catalogo(self) -> list[PruebaCatalogo]:
        ultimas: dict[str, dict] = {}
        for doc in self.unidad.database.catalogo_pruebas.find({"activo": True}):
            actual = ultimas.get(doc["codigo"])
            if actual is None or doc["version"] > actual["version"]:
                ultimas[doc["codigo"]] = doc
        return [
            PruebaCatalogo(
                doc["codigo"],
                doc["nombre"],
                doc["version"],
                tuple(_parametro(p) for p in doc["parametros"]),
                doc.get("tipo_muestra"),
                doc.get("indicaciones"),
            )
            for doc in sorted(ultimas.values(), key=lambda d: (d["nombre"].lower(), d["codigo"]))
        ]

    @staticmethod
    def _a_orden(doc: dict) -> Orden:
        return Orden(
            id_orden=str(doc["_id"]),
            numero_orden=doc["numero_orden"],
            id_paciente=str(doc["id_paciente"]),
            id_consulta=str(doc["id_consulta"]),
            id_profesional=doc["id_profesional_central"],
            estado=ESTADO_ORDEN_DOMINIO[doc["estado"]],
            solicitada_en=con_utc(doc["solicitada_en"]),
            pruebas=tuple(
                PruebaOrden(
                    p["codigo"],
                    p["nombre"],
                    p["version"],
                    tuple(_parametro(x) for x in p.get("parametros", [])),
                    tuple(_resultado(x) for x in p.get("resultados", [])),
                    p.get("observaciones"),
                    p.get("registrado_por"),
                    con_utc(p["registrado_en"]) if p.get("registrado_en") else None,
                )
                for p in doc["pruebas"]
            ),
            muestras=tuple(
                Muestra(
                    m["codigo"],
                    m["tipo"],
                    con_utc(m["tomada_en"]),
                    m.get("condicion"),
                    m.get("observaciones"),
                )
                for m in doc.get("muestras", [])
            ),
            validada_en=con_utc(doc["validada_en"]) if doc.get("validada_en") else None,
            validada_por=doc.get("validada_por"),
            motivo_cancelacion=doc.get("motivo_cancelacion"),
        )

    def obtener(self, id_paciente: str, id_orden: str) -> Orden | None:
        paciente, orden = _identificador(id_paciente), _identificador(id_orden)
        if paciente is None or orden is None:
            return None
        doc = self.coleccion.find_one({"_id": orden, "id_paciente": paciente})
        return self._a_orden(doc) if doc else None

    def listar(self, id_paciente: str, limite: int) -> list[Orden]:
        paciente = _identificador(id_paciente)
        if paciente is None:
            return []
        cursor = (
            self.coleccion.find({"id_paciente": paciente})
            .sort([("solicitada_en", -1), ("_id", -1)])
            .limit(limite)
        )
        return [self._a_orden(d) for d in cursor]

    # --- escritura -----------------------------------------------------------------------

    def _uuid(self, id_profesional: str) -> str:
        try:
            return str(UUID(id_profesional))
        except ValueError as error:
            raise ProfesionalNoVinculado("La cuenta no es valida.") from error

    def _cambiar_si_abierta(
        self, identificador: ObjectId, paciente: ObjectId, cambios: dict[str, Any], **extra: Any
    ) -> None:
        """Actualizacion condicional: solo si la orden sigue abierta."""

        def escribir() -> None:
            resultado = self.coleccion.update_one(
                {"_id": identificador, "id_paciente": paciente, "estado": {"$in": ABIERTAS_BD}},
                cambios,
                **extra,
            )
            if resultado.matched_count == 0:
                raise ConflictoEstado("La orden cambio de estado mientras se procesaba.")

        self.unidad.pendientes.append(escribir)

    def solicitar(
        self, id_paciente: str, id_consulta: str, id_profesional: str, codigos: tuple[str, ...]
    ) -> Orden:
        paciente, consulta = _identificador(id_paciente), _identificador(id_consulta)
        if paciente is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if consulta is None:
            raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")
        quien = self._uuid(id_profesional)
        catalogo = {p.codigo: p for p in self.listar_catalogo()}
        desconocidas = [c for c in codigos if c not in catalogo]
        if desconocidas:
            raise DatosInvalidos(
                "Pruebas inexistentes o inactivas en el catalogo: " + ", ".join(desconocidas)
            )
        ahora = _milisegundos(datetime.now(UTC))
        identificador = ObjectId()
        pruebas = [catalogo[c] for c in codigos]
        numero = f"ORD-{ahora:%Y%m%d}-{uuid4().hex[:8].upper()}"
        documento = {
            "_id": identificador,
            "numero_orden": numero,
            "id_paciente": paciente,
            "id_consulta": consulta,
            "id_profesional_central": quien,
            "estado": ESTADO_ORDEN_BD[EstadoOrden.SOLICITADA],
            "solicitada_en": ahora,
            "muestras": [],
            "pruebas": [
                {
                    "codigo": p.codigo,
                    "nombre": p.nombre,
                    "version": p.version,
                    "parametros": [_doc_parametro(x) for x in p.parametros],
                    "resultados": [],
                }
                for p in pruebas
            ],
        }

        def insertar() -> None:
            # Punto de serializacion con la baja del paciente (igual que registrar_consulta).
            guarda = self.unidad.database.pacientes.update_one(
                {"_id": paciente, "estado": ESTADO_ACTIVO}, {"$set": {"actualizado_en": ahora}}
            )
            if guarda.matched_count == 0:
                raise PacienteArchivado("El historial esta archivado; no admite cambios.")
            try:
                self.coleccion.insert_one(documento)
            except DuplicateKeyError as error:
                if "numero_orden" not in str(error):
                    raise
                raise IntegracionNoConfigurada(
                    "No se pudo asignar el numero de orden; intenta de nuevo."
                ) from error

        self.unidad.pendientes.append(insertar)
        return Orden(
            str(identificador),
            numero,
            id_paciente,
            id_consulta,
            quien,
            EstadoOrden.SOLICITADA,
            ahora,
            tuple(PruebaOrden(p.codigo, p.nombre, p.version, p.parametros) for p in pruebas),
        )

    def _existente(self, id_paciente: str, id_orden: str) -> tuple[ObjectId, ObjectId, Orden]:
        paciente, identificador = _identificador(id_paciente), _identificador(id_orden)
        orden = self.obtener(id_paciente, id_orden)
        if paciente is None or identificador is None or orden is None:
            raise RegistroNoEncontrado("La orden no existe en el historial del paciente.")
        return identificador, paciente, orden

    def registrar_muestra(
        self, id_paciente: str, id_orden: str, muestra: NuevaMuestra, ahora: datetime
    ) -> Orden:
        identificador, paciente, orden = self._existente(id_paciente, id_orden)
        codigo = f"M{len(orden.muestras) + 1}"
        tomada = _milisegundos(con_utc(muestra.tomada_en or ahora))
        doc = _sin_vacios(
            {
                "codigo": codigo,
                "tipo": muestra.tipo,
                "tomada_en": tomada,
                "condicion": _limpio(muestra.condicion),
                "observaciones": _limpio(muestra.observaciones),
            }
        )
        self._cambiar_si_abierta(identificador, paciente, {"$push": {"muestras": doc}})
        nueva = Muestra(codigo, muestra.tipo, tomada, muestra.condicion, muestra.observaciones)
        return replace(orden, muestras=(*orden.muestras, nueva))

    def registrar_resultados(
        self,
        id_paciente: str,
        id_orden: str,
        codigo_prueba: str,
        resultados: tuple[Resultado, ...],
        observaciones: str | None,
        id_profesional: str,
        ahora: datetime,
    ) -> Orden:
        identificador, paciente, orden = self._existente(id_paciente, id_orden)
        quien = self._uuid(id_profesional)
        momento = _milisegundos(ahora)
        poner: dict[str, Any] = {
            "pruebas.$[p].resultados": [_doc_resultado(r) for r in resultados],
            "pruebas.$[p].registrado_por": quien,
            "pruebas.$[p].registrado_en": momento,
            "estado": ESTADO_ORDEN_BD[EstadoOrden.EN_PROCESO],
        }
        if _limpio(observaciones):
            poner["pruebas.$[p].observaciones"] = observaciones
        self._cambiar_si_abierta(
            identificador,
            paciente,
            {"$set": poner},
            array_filters=[{"p.codigo": codigo_prueba}],
        )
        pruebas = tuple(
            replace(
                p,
                resultados=resultados,
                observaciones=_limpio(observaciones) or p.observaciones,
                registrado_por=quien,
                registrado_en=momento,
            )
            if p.codigo == codigo_prueba
            else p
            for p in orden.pruebas
        )
        return replace(orden, pruebas=pruebas, estado=EstadoOrden.EN_PROCESO)

    def validar(
        self, id_paciente: str, id_orden: str, id_profesional: str, ahora: datetime
    ) -> Orden:
        identificador, paciente, orden = self._existente(id_paciente, id_orden)
        quien = self._uuid(id_profesional)
        momento = _milisegundos(ahora)
        self._cambiar_si_abierta(
            identificador,
            paciente,
            {
                "$set": {
                    "estado": ESTADO_ORDEN_BD[EstadoOrden.VALIDADA],
                    "validada_en": momento,
                    "validada_por": quien,
                }
            },
        )
        return replace(orden, estado=EstadoOrden.VALIDADA, validada_en=momento, validada_por=quien)

    def cancelar(
        self, id_paciente: str, id_orden: str, motivo: str, id_profesional: str, ahora: datetime
    ) -> Orden:
        identificador, paciente, orden = self._existente(id_paciente, id_orden)
        quien = self._uuid(id_profesional)
        self._cambiar_si_abierta(
            identificador,
            paciente,
            {
                "$set": {
                    "estado": ESTADO_ORDEN_BD[EstadoOrden.CANCELADA],
                    "motivo_cancelacion": motivo,
                    "cancelada_por": quien,
                    "cancelada_en": _milisegundos(ahora),
                }
            },
        )
        return replace(orden, estado=EstadoOrden.CANCELADA, motivo_cancelacion=motivo)


class UnidadTrabajoMongo:
    """Acumula escrituras y las ejecuta en commit(); sin commit() no se guarda nada."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.pendientes: list[Callable[[], None]] = []

    def __enter__(self) -> Self:
        self.pendientes = []
        self.pacientes = RepositorioPacientesMongo(self)
        self.historial = RepositorioHistorialMongo(self)
        self.profesionales = RepositorioProfesionalesMongo(self)
        self.citas = RepositorioCitasMongo(self)
        self.laboratorio = RepositorioLaboratorioMongo(self)
        # El odontograma es propio de la clinica odontologica: aqui responde 501.
        pendientes = repositorios_pendientes(MOTOR)
        self.odontograma = pendientes["odontograma"]
        self.crecimiento = pendientes["crecimiento"]
        self.vacunacion = pendientes["vacunacion"]
        self.hospital = pendientes["hospital"]
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        self.pendientes = []
        if isinstance(exc_value, WriteError) and exc_value.code == VALIDACION_DOCUMENTO:
            raise DatosInvalidos("Los datos no cumplen las reglas del laboratorio.") from exc_value
        if isinstance(exc_value, PyMongoError):
            # Errores de base no previstos por el adaptador: sin detalles hacia el cliente.
            raise IntegracionNoConfigurada(
                "La base del laboratorio no esta disponible."
            ) from exc_value
        return False

    def commit(self) -> None:
        pendientes, self.pendientes = self.pendientes, []
        for escribir in pendientes:
            escribir()

    def rollback(self) -> None:
        self.pendientes = []
