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
from app.domain.consulta import Consulta, Diagnostico, NuevaConsulta, Receta, Tratamiento
from app.domain.errores import (
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
)
from app.domain.paciente import Alergia, Baja, Contacto, NuevoPaciente, Paciente
from app.infrastructure.persistence.comun import con_utc
from app.infrastructure.persistence.pendiente import repositorios_pendientes

MOTOR = "MongoDB"
ESTADO_ACTIVO = "Activo"
ESTADO_ARCHIVADO = "Archivado"
VALIDACION_DOCUMENTO = 121  # el documento no cumple el $jsonSchema de la coleccion
ORDEN_NOMBRE = Collation(locale="es", strength=1)  # sin mayusculas ni acentos


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
            documento["alergias"] = [
                _sin_vacios(
                    {
                        "sustancia": a.sustancia,
                        "reaccion": _limpio(a.reaccion),
                        "severidad": _limpio(a.severidad),
                    }
                )
                for a in datos.alergias
            ]

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
            "diagnosticos": [
                _sin_vacios(
                    {
                        "descripcion": d.descripcion,
                        "codigo": _limpio(d.codigo),
                        "sistema_codigo": _limpio(d.sistema_codigo),
                    }
                )
                for d in datos.diagnosticos
            ],
            "tratamientos": [{"descripcion": t.descripcion} for t in datos.tratamientos],
            "recetas": [
                _sin_vacios(
                    {
                        "medicamento": r.medicamento,
                        "dosis": r.dosis,
                        "frecuencia": r.frecuencia,
                        "via_administracion": _limpio(r.via_administracion),
                        "duracion_dias": r.duracion_dias,
                        "instrucciones": _limpio(r.instrucciones),
                    }
                )
                for r in datos.recetas
            ],
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
        return [
            Consulta(
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
            for row in cursor
        ]


class UnidadTrabajoMongo:
    """Acumula escrituras y las ejecuta en commit(); sin commit() no se guarda nada."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.pendientes: list[Callable[[], None]] = []

    def __enter__(self) -> Self:
        self.pendientes = []
        self.pacientes = RepositorioPacientesMongo(self)
        self.historial = RepositorioHistorialMongo(self)
        # Citas, perfiles y odontograma: pendientes en este motor (HTTP 501).
        for nombre, repositorio in repositorios_pendientes(MOTOR).items():
            if nombre not in ("pacientes", "historial"):
                setattr(self, nombre, repositorio)
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
