"""Centro Pediatrico (MySQL): registrar paciente, historial, consultas, archivo y busqueda.

Una solicitud = una conexion = una transaccion. Todo lo que escribe un caso de uso
(consulta + diagnosticos + tratamientos + recetas) se confirma junto en commit() o no
se guarda. Correspondencia con el contrato comun:

    paciente        -> paciente (+ paciente_alergia / alergias_conocidas)
    consulta        -> consulta_medica
    diagnosticos    -> consulta_diagnostico (el primero es el principal)
    tratamientos    -> consulta_tratamiento
    recetas         -> recetas_medicamento

Las reglas de integridad (expediente archivado, medico inactivo) tambien las impone la
base con triggers (002_integridad.sql); aqui se comprueban antes para dar el error correcto.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Literal, Self
from uuid import UUID, uuid4

import pymysql
from pymysql.err import IntegrityError, OperationalError

from app.application.errores import IntegracionNoConfigurada
from app.domain.consulta import Consulta, Diagnostico, NuevaConsulta, Receta, Tratamiento
from app.domain.errores import (
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
)
from app.domain.paciente import Alergia, Baja, Contacto, NuevoPaciente, Paciente
from app.infrastructure.persistence.comun import (
    con_utc,
    entero_positivo,
    escapar_like,
    utc_ingenuo,
)
from app.infrastructure.persistence.pendiente import repositorios_pendientes

MOTOR = "MySQL"
ER_SIGNAL_EXCEPTION = 1644  # SIGNAL SQLSTATE '45000' de los triggers de 002_integridad.sql
ER_DUP_ENTRY = 1062
COLACION = "utf8mb4_0900_ai_ci"  # sin mayusculas ni acentos, igual que la regla comun


def _traducir_trigger(error: OperationalError) -> Exception | None:
    """Convierte los mensajes de los triggers en errores del dominio (o None si no aplica)."""
    codigo = error.args[0] if error.args else None
    if codigo != ER_SIGNAL_EXCEPTION or len(error.args) < 2:
        return None
    mensaje = str(error.args[1]).lower()
    if "archivado" in mensaje:
        return PacienteArchivado("El historial esta archivado; no admite consultas nuevas.")
    if "inactivo" in mensaje:
        return ProfesionalNoVinculado("Tu cuenta esta inactiva en el Centro Pediatrico.")
    if "nacimiento" in mensaje:
        return DatosInvalidos(str(error.args[1]))
    return None


class RepositorioPacientesMySQL:
    def __init__(self, conexion: pymysql.Connection) -> None:
        self.conexion = conexion

    def _una_fila(self, sql: str, parametros: tuple = ()) -> tuple | None:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.fetchone()

    def _filas(self, sql: str, parametros: tuple = ()) -> tuple[tuple, ...]:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.fetchall()

    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        numero = entero_positivo(id_paciente)
        if numero is None:
            return None
        fila = self._una_fila(
            "SELECT id_paciente, nombre, apellido, fecha_nacimiento, archivado, telefono, "
            "correo_electronico, direccion, alergias_evaluadas "
            "FROM paciente WHERE id_paciente = %s",
            (numero,),
        )
        if fila is None:
            return None
        alergias = None
        if fila[8]:
            alergias = tuple(
                Alergia(sustancia, reaccion, severidad)
                for sustancia, reaccion, severidad in self._filas(
                    "SELECT a.nombre, pa.reaccion, pa.severidad FROM paciente_alergia pa "
                    "JOIN alergias_conocidas a ON a.id_alergias = pa.id_alergias "
                    "WHERE pa.id_paciente = %s ORDER BY a.nombre",
                    (numero,),
                )
            )
        return Paciente(
            str(fila[0]),
            fila[1],
            fila[2],
            fila[3],
            archivado=bool(fila[4]),
            contacto=Contacto(fila[5], fila[6], fila[7]) if fila[5] or fila[6] or fila[7] else None,
            alergias=alergias,
        )

    def registrar(self, datos: NuevoPaciente) -> Paciente:
        if datos.fecha_nacimiento is None:
            # En este hospital pediatrico la edad define la atencion: la columna es obligatoria.
            raise DatosInvalidos("En el Centro Pediatrico la fecha de nacimiento es obligatoria.")
        contacto = datos.contacto or Contacto()
        try:
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO paciente (numero_expediente, nombre, apellido, fecha_nacimiento, "
                    "id_estado_fk, alergias_evaluadas, telefono, correo_electronico, direccion) "
                    "VALUES (%s, %s, %s, %s, "
                    "(SELECT id_estado FROM estado WHERE nombre = 'Activo'), %s, %s, %s, %s)",
                    (
                        "CP-" + uuid4().hex[:20].upper(),
                        datos.nombres,
                        datos.apellidos,
                        datos.fecha_nacimiento,
                        datos.alergias is not None,
                        contacto.telefono,
                        contacto.correo,
                        contacto.direccion,
                    ),
                )
                id_nuevo = cursor.lastrowid
        except OperationalError as error:
            traducido = _traducir_trigger(error)
            if traducido is not None:
                raise traducido from error
            raise
        for alergia in datos.alergias or ():
            self._guardar_alergia(id_nuevo, alergia)
        return Paciente(
            str(id_nuevo),
            datos.nombres,
            datos.apellidos,
            datos.fecha_nacimiento,
            contacto=datos.contacto,
            alergias=datos.alergias,
        )

    def _guardar_alergia(self, id_paciente: int, alergia: Alergia) -> None:
        # Catalogo compartido: "Latex" y "latex" son la misma sustancia (colacion _ai_ci).
        # La cuenta de la API puede insertar pero no actualizar: SELECT, luego INSERT.
        consulta = "SELECT id_alergias FROM alergias_conocidas WHERE nombre = %s"
        fila = self._una_fila(consulta, (alergia.sustancia,))
        if fila is None:
            try:
                with self.conexion.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO alergias_conocidas (nombre) VALUES (%s)", (alergia.sustancia,)
                    )
            except IntegrityError as error:
                if error.args[0] != ER_DUP_ENTRY:
                    raise
                # Otra solicitud la creo justo ahora: se reutiliza.
            fila = self._una_fila(consulta, (alergia.sustancia,))
        with self.conexion.cursor() as cursor:
            cursor.execute(
                "INSERT INTO paciente_alergia (id_paciente, id_alergias, reaccion, severidad) "
                "VALUES (%s, %s, %s, %s)",
                (id_paciente, fila[0], alergia.reaccion, alergia.severidad),
            )

    def buscar(self, palabras: tuple[str, ...], limite: int) -> list[Paciente]:
        # Regla comun (domain/busqueda.py): cada palabra es el comienzo de alguna palabra del
        # nombre. La colacion _ai_ci ignora mayusculas y acentos.
        nombre = f"CONCAT(nombre, ' ', apellido) COLLATE {COLACION}"
        condiciones = []
        parametros: list[Any] = []
        for palabra in palabras:
            condiciones.append(
                f"({nombre} LIKE %s ESCAPE '\\\\' OR {nombre} LIKE %s ESCAPE '\\\\')"
            )
            parametros += [f"{escapar_like(palabra)}%", f"% {escapar_like(palabra)}%"]
        filas = self._filas(
            "SELECT id_paciente, nombre, apellido, fecha_nacimiento, archivado FROM paciente "
            "WHERE " + " AND ".join(condiciones) + " "
            "ORDER BY apellido, nombre, id_paciente LIMIT %s",
            (*parametros, limite),
        )
        return [Paciente(str(f[0]), f[1], f[2], f[3], archivado=bool(f[4])) for f in filas]

    def archivar(self, id_paciente: str, baja: Baja) -> None:
        numero = entero_positivo(id_paciente)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        try:
            quien = str(UUID(baja.id_profesional))
        except ValueError as error:
            raise ProfesionalNoVinculado("La cuenta no es valida para dar de baja.") from error
        # Condicional: si otra solicitud lo archivo primero, no se sobrescribe su baja.
        with self.conexion.cursor() as cursor:
            cambiados = cursor.execute(
                "UPDATE paciente SET archivado = TRUE, fecha_baja = %s, motivo_baja = %s, "
                "detalle_baja = %s, archivado_por = %s "
                "WHERE id_paciente = %s AND archivado = FALSE",
                (utc_ingenuo(baja.fecha), baja.motivo.value, baja.detalle, quien, numero),
            )
        if cambiados == 0:
            if self._una_fila("SELECT 1 FROM paciente WHERE id_paciente = %s", (numero,)) is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            raise PacienteArchivado("El historial ya estaba archivado.")


class RepositorioHistorialMySQL:
    def __init__(self, conexion: pymysql.Connection) -> None:
        self.conexion = conexion

    def _filas(self, sql: str, parametros: tuple = ()) -> tuple[tuple, ...]:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.fetchall()

    def _id_medico(self, id_profesional: str) -> int:
        try:
            uuid = str(UUID(id_profesional))
        except ValueError as error:
            raise ProfesionalNoVinculado(
                "Tu cuenta no es un profesional de este hospital."
            ) from error
        filas = self._filas(
            "SELECT id_medico FROM medico WHERE id_profesional_central = %s AND activo = TRUE",
            (uuid,),
        )
        if not filas:
            raise ProfesionalNoVinculado(
                "Tu cuenta no esta vinculada a un medico activo del Centro Pediatrico. "
                "Pide que ejecuten: python -m scripts.sincronizar_profesionales"
            )
        return filas[0][0]

    def registrar_consulta(
        self, id_paciente: str, id_profesional: str, datos: NuevaConsulta
    ) -> Consulta:
        numero = entero_positivo(id_paciente)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        id_medico = self._id_medico(id_profesional)
        # Bloquea la fila del paciente durante la transaccion: una baja concurrente espera
        # a que esta consulta termine (o esta consulta ve la baja y se rechaza).
        filas = self._filas(
            "SELECT archivado FROM paciente WHERE id_paciente = %s FOR UPDATE", (numero,)
        )
        if not filas:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if filas[0][0]:
            raise PacienteArchivado("El historial esta archivado; no admite consultas nuevas.")

        ahora = datetime.now(UTC)
        fecha = utc_ingenuo(ahora)
        try:
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO consulta_medica (id_paciente, id_medico, fecha_hora, "
                    "motivo_consulta, notas_medicas) VALUES (%s, %s, %s, %s, %s)",
                    (numero, id_medico, fecha, datos.motivo, datos.notas),
                )
                id_consulta = cursor.lastrowid
                for posicion, d in enumerate(datos.diagnosticos):
                    cursor.execute(
                        "INSERT INTO consulta_diagnostico (id_consulta, codigo, sistema_codigo, "
                        "descripcion, es_principal) VALUES (%s, %s, %s, %s, %s)",
                        (id_consulta, d.codigo, d.sistema_codigo, d.descripcion, posicion == 0),
                    )
                for t in datos.tratamientos:
                    cursor.execute(
                        "INSERT INTO consulta_tratamiento (id_consulta, descripcion) "
                        "VALUES (%s, %s)",
                        (id_consulta, t.descripcion),
                    )
                for r in datos.recetas:
                    cursor.execute(
                        "INSERT INTO recetas_medicamento (id_consulta, medicamento, dosis, "
                        "frecuencia, duracion_dias, via_administracion, "
                        "instrucciones_adicionales, fecha_emitida) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            id_consulta,
                            r.medicamento,
                            r.dosis,
                            r.frecuencia,
                            r.duracion_dias,
                            r.via_administracion,
                            r.instrucciones,
                            fecha,
                        ),
                    )
        except OperationalError as error:
            traducido = _traducir_trigger(error)
            if traducido is not None:
                raise traducido from error
            raise
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
        numero = entero_positivo(id_paciente)
        if numero is None:
            return []
        filtro, parametros = "", [numero]
        if antes_de is not None:
            filtro = "AND c.fecha_hora < %s "
            parametros.append(utc_ingenuo(antes_de))
        filas = self._filas(
            "SELECT c.id_consulta, COALESCE(m.id_profesional_central, "
            "CONCAT('sin-cuenta-', m.id_medico)), c.fecha_hora, c.motivo_consulta, "
            "c.notas_medicas FROM consulta_medica c JOIN medico m ON m.id_medico = c.id_medico "
            "WHERE c.id_paciente = %s "
            + filtro
            + "ORDER BY c.fecha_hora DESC, c.id_consulta DESC LIMIT %s",
            (*parametros, limite),
        )
        if not filas:
            return []
        ids = tuple(f[0] for f in filas)
        marcas = ", ".join(["%s"] * len(ids))
        diagnosticos: dict[int, list[Diagnostico]] = {i: [] for i in ids}
        tratamientos: dict[int, list[Tratamiento]] = {i: [] for i in ids}
        recetas: dict[int, list[Receta]] = {i: [] for i in ids}
        for id_consulta, descripcion, codigo, sistema in self._filas(
            "SELECT id_consulta, descripcion, codigo, sistema_codigo FROM consulta_diagnostico "
            f"WHERE id_consulta IN ({marcas}) ORDER BY id_diagnostico",
            ids,
        ):
            diagnosticos[id_consulta].append(Diagnostico(descripcion, codigo, sistema))
        for id_consulta, descripcion in self._filas(
            "SELECT id_consulta, descripcion FROM consulta_tratamiento "
            f"WHERE id_consulta IN ({marcas}) ORDER BY id_tratamiento",
            ids,
        ):
            tratamientos[id_consulta].append(Tratamiento(descripcion))
        for fila in self._filas(
            "SELECT id_consulta, medicamento, dosis, frecuencia, via_administracion, "
            "duracion_dias, instrucciones_adicionales FROM recetas_medicamento "
            f"WHERE id_consulta IN ({marcas}) ORDER BY id_receta",
            ids,
        ):
            recetas[fila[0]].append(Receta(fila[1], fila[2], fila[3], fila[4], fila[5], fila[6]))
        return [
            Consulta(
                str(f[0]),
                id_paciente,
                str(f[1]),
                con_utc(f[2]),
                f[3],
                f[4],
                tuple(diagnosticos[f[0]]),
                tuple(tratamientos[f[0]]),
                tuple(recetas[f[0]]),
            )
            for f in filas
        ]


class UnidadTrabajoMySQL:
    """Cada solicitud abre su conexion y la cierra; sin commit() todo se revierte."""

    def __init__(self, conectar: Callable[[], pymysql.Connection]) -> None:
        self._conectar = conectar
        self.conexion: pymysql.Connection | None = None

    def __enter__(self) -> Self:
        try:
            self.conexion = self._conectar()
        except pymysql.MySQLError as error:
            raise IntegracionNoConfigurada("La base clinica no esta disponible.") from error
        self.pacientes = RepositorioPacientesMySQL(self.conexion)
        self.historial = RepositorioHistorialMySQL(self.conexion)
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
        try:
            self.rollback()
        finally:
            self.conexion.close()
        if isinstance(exc_value, pymysql.MySQLError):
            # Errores de base no previstos por el adaptador: sin detalles hacia el cliente.
            raise IntegracionNoConfigurada("La consulta clinica no esta disponible.") from exc_value
        return False

    def commit(self) -> None:
        self.conexion.commit()

    def rollback(self) -> None:
        self.conexion.rollback()
