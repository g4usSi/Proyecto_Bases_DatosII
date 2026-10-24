from types import TracebackType
from typing import Literal, Self

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.application.errores import IntegracionNoConfigurada
from app.domain.paciente import Alergia, Baja, Contacto, NuevoPaciente, Paciente
from app.infrastructure.persistence.pendiente import pendiente, repositorios_pendientes


def _contacto(valor: dict | None) -> Contacto | None:
    if not valor:
        return None
    return Contacto(valor.get("telefono"), valor.get("correo"), valor.get("direccion"))


def _alergias(row: dict) -> tuple[Alergia, ...]:
    return tuple(
        Alergia(a["sustancia"], a.get("reaccion"), a.get("severidad"))
        for a in row.get("alergias", [])
    )


class RepositorioPacientesMongo:
    def __init__(self, database: Database) -> None:
        self.database = database

    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        try:
            identificador = ObjectId(id_paciente)
        except InvalidId:
            return None
        try:
            row = self.database.pacientes.find_one(
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
        except PyMongoError as error:
            raise IntegracionNoConfigurada("La base del laboratorio no esta disponible.") from error
        if row is None:
            return None
        fecha = row.get("fecha_nacimiento")
        return Paciente(
            str(row["_id"]),
            row["nombres"],
            row["apellidos"],
            fecha.date() if fecha else None,
            archivado=row.get("estado") == "Archivado",
            contacto=_contacto(row.get("contacto")),
            alergias=_alergias(row) if row.get("alergias_evaluadas") else None,
        )

    def registrar(self, datos: NuevoPaciente) -> Paciente:
        pendiente("MongoDB", "registrar paciente")

    def archivar(self, id_paciente: str, baja: Baja) -> None:
        pendiente("MongoDB", "archivar historial")


class UnidadTrabajoLecturaMongo:
    """Solo lectura de un documento; no promete transacciones entre colecciones."""

    def __init__(self, database: Database) -> None:
        self.pacientes = RepositorioPacientesMongo(database)
        for nombre, repositorio in repositorios_pendientes("MongoDB").items():
            setattr(self, nombre, repositorio)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        return False

    def commit(self) -> None:
        raise IntegracionNoConfigurada("El adaptador de escritura MongoDB esta pendiente.")

    def rollback(self) -> None:
        pass  # Esta unidad no ejecuta escrituras.
