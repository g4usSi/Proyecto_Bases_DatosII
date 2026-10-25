"""Centro Pediatrico (MySQL): tutores (tabla tutor) y su vinculo con el paciente
(paciente_tutor: parentesco, principal y autorizacion para recogerlo).

El principal unico lo garantiza el indice uq_tutor_principal; el cambio de principal se hace
en la misma transaccion bloqueando al paciente, asi dos cambios simultaneos no chocan.
"""

import pymysql
from pymysql.err import IntegrityError, OperationalError

from app.domain.errores import (
    ConflictoEstado,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    RegistroNoEncontrado,
)
from app.domain.tutores import CambiosTutor, NuevoTutor, Tutor, TutorDePaciente, Vinculo
from app.infrastructure.persistence.comun import entero_positivo

ER_DUP_ENTRY = 1062
ER_SIGNAL_EXCEPTION = 1644
ER_CHECK_VIOLADO = 3819

_COLUMNAS = (
    "t.id_tutor, t.nombre, t.apellido, t.dpi_pasaporte, t.telefono, t.correo_electronico, "
    "t.direccion"
)


def _tutor(fila: tuple) -> Tutor:
    return Tutor(str(fila[0]), fila[1], fila[2], fila[3], fila[4], fila[5], fila[6])


class RepositorioTutoresMySQL:
    def __init__(self, conexion: pymysql.Connection) -> None:
        self.conexion = conexion

    def _filas(self, sql: str, parametros: tuple = ()) -> tuple[tuple, ...]:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.fetchall()

    def _ejecutar(self, sql: str, parametros: tuple = ()) -> int:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.lastrowid

    def _bloquear_paciente(self, id_paciente: str) -> int:
        numero = entero_positivo(id_paciente)
        filas = (
            self._filas(
                "SELECT archivado FROM paciente WHERE id_paciente = %s FOR UPDATE", (numero,)
            )
            if numero is not None
            else ()
        )
        if not filas:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if filas[0][0]:
            raise PacienteArchivado("El historial esta archivado; no admite cambios.")
        return numero

    def _uno(self, paciente: int, tutor: int) -> TutorDePaciente | None:
        filas = self._filas(
            f"SELECT {_COLUMNAS}, pt.parentesco, pt.es_principal, pt.autorizado "
            "FROM paciente_tutor pt JOIN tutor t ON t.id_tutor = pt.id_tutor "
            "WHERE pt.id_paciente = %s AND pt.id_tutor = %s",
            (paciente, tutor),
        )
        if not filas:
            return None
        f = filas[0]
        return TutorDePaciente(_tutor(f), f[7], bool(f[8]), bool(f[9]))

    def listar(self, id_paciente: str) -> list[TutorDePaciente]:
        numero = entero_positivo(id_paciente)
        if numero is None:
            return []
        return [
            TutorDePaciente(_tutor(f), f[7], bool(f[8]), bool(f[9]))
            for f in self._filas(
                f"SELECT {_COLUMNAS}, pt.parentesco, pt.es_principal, pt.autorizado "
                "FROM paciente_tutor pt JOIN tutor t ON t.id_tutor = pt.id_tutor "
                "WHERE pt.id_paciente = %s "
                "ORDER BY pt.es_principal DESC, t.apellido, t.nombre, t.id_tutor",
                (numero,),
            )
        ]

    def buscar_por_documento(self, documento: str) -> Tutor | None:
        filas = self._filas(
            f"SELECT {_COLUMNAS} FROM tutor t WHERE t.dpi_pasaporte = %s", (documento,)
        )
        return _tutor(filas[0]) if filas else None

    def _quitar_principal(self, paciente: int, excepto: int) -> None:
        with self.conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE paciente_tutor SET es_principal = FALSE "
                "WHERE id_paciente = %s AND es_principal AND id_tutor <> %s",
                (paciente, excepto),
            )

    def vincular(
        self,
        id_paciente: str,
        vinculo: Vinculo,
        id_tutor: str | None = None,
        nuevo: NuevoTutor | None = None,
    ) -> TutorDePaciente:
        paciente = self._bloquear_paciente(id_paciente)
        if nuevo is not None:
            try:
                tutor = self._ejecutar(
                    "INSERT INTO tutor (nombre, apellido, dpi_pasaporte, telefono, "
                    "correo_electronico, direccion) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        nuevo.nombres,
                        nuevo.apellidos,
                        nuevo.documento,
                        nuevo.telefono,
                        nuevo.correo,
                        nuevo.direccion,
                    ),
                )
            except IntegrityError as error:
                if error.args[0] == ER_DUP_ENTRY:
                    raise ConflictoEstado(
                        "Ya existe un tutor con ese documento: vinculalo con su id_tutor."
                    ) from error
                raise
        else:
            tutor = entero_positivo(id_tutor or "")
            if tutor is None or not self._filas(
                "SELECT 1 FROM tutor WHERE id_tutor = %s", (tutor,)
            ):
                raise RegistroNoEncontrado("El tutor no existe.")
        if vinculo.es_principal:
            self._quitar_principal(paciente, tutor)
        try:
            self._ejecutar(
                "INSERT INTO paciente_tutor (id_paciente, id_tutor, parentesco, es_principal, "
                "autorizado) VALUES (%s, %s, %s, %s, %s)",
                (paciente, tutor, vinculo.parentesco, vinculo.es_principal, vinculo.autorizado),
            )
        except IntegrityError as error:
            if error.args[0] == ER_DUP_ENTRY:
                raise ConflictoEstado("Ese tutor ya esta vinculado al paciente.") from error
            raise
        except OperationalError as error:
            if error.args and error.args[0] == ER_SIGNAL_EXCEPTION:
                raise PacienteArchivado("El historial esta archivado.") from error
            raise
        resultado = self._uno(paciente, tutor)
        assert resultado is not None
        return resultado

    def cambiar(self, id_paciente: str, id_tutor: str, cambios: CambiosTutor) -> TutorDePaciente:
        paciente = self._bloquear_paciente(id_paciente)
        tutor = entero_positivo(id_tutor)
        actual = self._uno(paciente, tutor) if tutor is not None else None
        if actual is None:
            raise RegistroNoEncontrado("Ese tutor no esta vinculado al paciente.")
        principal = actual.es_principal if cambios.es_principal is None else cambios.es_principal
        autorizado = actual.autorizado if cambios.autorizado is None else cambios.autorizado
        if principal and not autorizado:
            raise DatosInvalidos("El tutor principal debe estar autorizado.")
        if cambios.es_principal:
            self._quitar_principal(paciente, tutor)
        vinculo = []
        valores: list = []
        for columna, valor in (
            ("parentesco", cambios.parentesco),
            ("es_principal", cambios.es_principal),
            ("autorizado", cambios.autorizado),
        ):
            if valor is not None:
                vinculo.append(f"{columna} = %s")
                valores.append(valor)
        try:
            if vinculo:
                with self.conexion.cursor() as cursor:
                    cursor.execute(
                        "UPDATE paciente_tutor SET "
                        + ", ".join(vinculo)
                        + " WHERE id_paciente = %s AND id_tutor = %s",
                        (*valores, paciente, tutor),
                    )
            contacto = []
            datos: list = []
            for columna, valor in (
                ("telefono", cambios.telefono),
                ("correo_electronico", cambios.correo),
                ("direccion", cambios.direccion),
            ):
                if valor is not None:
                    contacto.append(f"{columna} = %s")
                    datos.append(valor or None)
            if contacto:
                with self.conexion.cursor() as cursor:
                    cursor.execute(
                        "UPDATE tutor SET " + ", ".join(contacto) + " WHERE id_tutor = %s",
                        (*datos, tutor),
                    )
        except pymysql.MySQLError as error:
            if error.args and error.args[0] == ER_CHECK_VIOLADO:
                raise DatosInvalidos("El tutor principal debe estar autorizado.") from error
            if error.args and error.args[0] == ER_SIGNAL_EXCEPTION:
                raise PacienteArchivado("El historial esta archivado.") from error
            raise
        resultado = self._uno(paciente, tutor)
        assert resultado is not None
        return resultado
