"""Adaptador inicial de lectura. Cada solicitud abre y cierra su propia transaccion."""

from collections.abc import Callable
from types import TracebackType
from typing import Any, Literal, Self

from app.application.errores import IntegracionNoConfigurada
from app.domain.paciente import Baja, NuevoPaciente, Paciente
from app.infrastructure.persistence.pendiente import pendiente, repositorios_pendientes


class RepositorioPacientesSQL:
    def __init__(self, conexion: Any, consulta: str, motor: str = "SQL") -> None:
        self.conexion = conexion
        self.consulta = consulta
        self.motor = motor

    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        if not id_paciente.isascii() or not id_paciente.isdecimal():
            return None
        numero = int(id_paciente)
        if not 0 < numero <= 2_147_483_647:
            return None
        with self.conexion.cursor() as cursor:
            cursor.execute(self.consulta, (numero,))
            row = cursor.fetchone()
        if row is None:
            return None
        return Paciente(str(row[0]), row[1], row[2], row[3])

    # TODO(rama del motor): mover a postgresql/ o mysql/ cuando cada SQL tenga su esquema.
    def registrar(self, datos: NuevoPaciente) -> Paciente:
        pendiente(self.motor, "registrar paciente")

    def archivar(self, id_paciente: str, baja: Baja) -> None:
        pendiente(self.motor, "archivar historial")


class UnidadTrabajoSQL:
    def __init__(
        self,
        conectar: Callable[[], Any],
        consulta: str,
        errores: tuple[type, ...],
        motor: str = "SQL",
    ) -> None:
        self.conectar = conectar
        self.consulta = consulta
        self.errores = errores
        self.motor = motor
        self.conexion: Any = None

    def __enter__(self) -> Self:
        try:
            self.conexion = self.conectar()
        except self.errores as error:
            raise IntegracionNoConfigurada("La base clinica no esta disponible.") from error
        self.pacientes = RepositorioPacientesSQL(self.conexion, self.consulta, self.motor)
        for nombre, repositorio in repositorios_pendientes(self.motor).items():
            setattr(self, nombre, repositorio)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        try:
            self.rollback()
        finally:
            self.conexion.close()
        if isinstance(exc_value, self.errores):
            raise IntegracionNoConfigurada("La consulta clinica no esta disponible.") from exc_value
        return False

    def commit(self) -> None:
        self.conexion.commit()

    def rollback(self) -> None:
        self.conexion.rollback()
