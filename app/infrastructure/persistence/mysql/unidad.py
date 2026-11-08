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
from datetime import UTC, date, datetime
from types import TracebackType
from typing import Any, Literal, Self
from uuid import UUID, uuid4

import pymysql
from pymysql.err import IntegrityError, OperationalError

from app.application.errores import IntegracionNoConfigurada
from app.domain.cita import TRANSICIONES, Cita, EstadoCita, NuevaCita
from app.domain.consulta import Adenda, Consulta, Diagnostico, NuevaConsulta, Receta, Tratamiento
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
from app.domain.paciente import Alergia, Baja, CambiosPaciente, Contacto, NuevoPaciente, Paciente
from app.domain.pediatria import (
    ControlCrecimiento,
    DescripcionVacuna,
    DosisVacuna,
    EstadoDosis,
    NuevoControl,
    TipoVacuna,
)
from app.domain.profesional import ProfesionalLocal
from app.infrastructure.persistence.comun import (
    con_utc,
    entero_positivo,
    escapar_like,
    utc_ingenuo,
)
from app.infrastructure.persistence.mysql.cobros import RepositorioCobrosMySQL
from app.infrastructure.persistence.mysql.tutores import RepositorioTutoresMySQL
from app.infrastructure.persistence.pendiente import repositorios_pendientes

MOTOR = "MySQL"
ER_SIGNAL_EXCEPTION = 1644  # SIGNAL SQLSTATE '45000' de los triggers de 002_integridad.sql
ER_DUP_ENTRY = 1062
ER_NO_REFERENCED_ROW = 1452  # clave foranea inexistente
ER_CHECK_VIOLATED = 3819
COLACION = "utf8mb4_0900_ai_ci"  # sin mayusculas ni acentos, igual que la regla comun


def _traducir_trigger(error: OperationalError) -> Exception | None:
    """Convierte los mensajes de los triggers en errores del dominio (o None si no aplica)."""
    codigo = error.args[0] if error.args else None
    if codigo != ER_SIGNAL_EXCEPTION or len(error.args) < 2:
        return None
    mensaje = str(error.args[1]).lower()
    if "ocupado" in mensaje:
        return ConflictoAgenda("El profesional ya tiene una cita en ese horario.")
    if "archivado" in mensaje:
        return PacienteArchivado("El historial esta archivado; no admite cambios.")
    if "inactivo" in mensaje:
        return ProfesionalNoVinculado("Tu cuenta esta inactiva en el Centro Pediatrico.")
    if "nacimiento" in mensaje:
        return DatosInvalidos(str(error.args[1]))
    if "rectificacion" in mensaje:
        return ConflictoEstado("Una dosis aplicada no se modifica.")
    return None


def _id_medico_activo(
    filas_de: Callable[[str, tuple], tuple[tuple, ...]], id_profesional: str
) -> int:
    try:
        uuid = str(UUID(id_profesional))
    except ValueError as error:
        raise ProfesionalNoVinculado("Tu cuenta no es un profesional de este hospital.") from error
    filas = filas_de(
        "SELECT id_medico FROM medico WHERE id_profesional_central = %s AND activo = TRUE",
        (uuid,),
    )
    if not filas:
        raise ProfesionalNoVinculado(
            "Tu cuenta no esta vinculada a un medico activo del Centro Pediatrico. "
            "Pide que ejecuten: python -m scripts.sincronizar_profesionales"
        )
    return filas[0][0]


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

    def actualizar(self, id_paciente: str, cambios: CambiosPaciente) -> None:
        numero = entero_positivo(id_paciente)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        asignaciones, parametros = [], []
        for columna, valor in (
            ("nombre", cambios.nombres),
            ("apellido", cambios.apellidos),
            ("fecha_nacimiento", cambios.fecha_nacimiento),
        ):
            if valor is not None:
                asignaciones.append(f"{columna} = %s")
                parametros.append(valor)
        if cambios.contacto is not None:  # reemplaza el contacto completo
            asignaciones += ["telefono = %s", "correo_electronico = %s", "direccion = %s"]
            parametros += [
                cambios.contacto.telefono,
                cambios.contacto.correo,
                cambios.contacto.direccion,
            ]
        try:
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "UPDATE paciente SET " + ", ".join(asignaciones) + " "
                    "WHERE id_paciente = %s AND archivado = FALSE",
                    (*parametros, numero),
                )
        except OperationalError as error:
            traducido = _traducir_trigger(error)
            if traducido is not None:
                raise traducido from error
            raise
        self._comprobar_activo(numero)

    def agregar_alergias(self, id_paciente: str, alergias: tuple[Alergia, ...]) -> None:
        numero = entero_positivo(id_paciente)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        with self.conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE paciente SET alergias_evaluadas = TRUE "
                "WHERE id_paciente = %s AND archivado = FALSE",
                (numero,),
            )
        self._comprobar_activo(numero)
        try:
            for alergia in alergias:
                self._guardar_alergia(numero, alergia)
        except IntegrityError as error:
            if error.args[0] != ER_DUP_ENTRY:
                raise
            raise DatosInvalidos("Esa alergia ya estaba registrada.") from error

    def _comprobar_activo(self, numero: int) -> None:
        """Tras un UPDATE condicional: MySQL cuenta 0 filas si nada cambio, asi que se consulta."""
        fila = self._una_fila("SELECT archivado FROM paciente WHERE id_paciente = %s", (numero,))
        if fila is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if fila[0]:
            raise PacienteArchivado("El historial esta archivado; no admite cambios.")


class RepositorioHistorialMySQL:
    def __init__(self, conexion: pymysql.Connection) -> None:
        self.conexion = conexion

    def _filas(self, sql: str, parametros: tuple = ()) -> tuple[tuple, ...]:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.fetchall()

    def _id_medico(self, id_profesional: str) -> int:
        return _id_medico_activo(self._filas, id_profesional)

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

    def obtener_consulta(self, id_paciente: str, id_consulta: str) -> Consulta | None:
        numero, consulta = entero_positivo(id_paciente), entero_positivo(id_consulta)
        if numero is None or consulta is None:
            return None
        consultas = self._cargar(id_paciente, numero, "AND c.id_consulta = %s ", [consulta], 1)
        return consultas[0] if consultas else None

    def agregar_a_consulta(
        self, id_paciente: str, id_consulta: str, id_profesional: str, adenda: Adenda
    ) -> Consulta:
        numero, consulta = entero_positivo(id_paciente), entero_positivo(id_consulta)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if consulta is None:
            raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")
        self._id_medico(id_profesional)  # exige un medico activo vinculado a la cuenta
        # Una baja concurrente espera a que termine esta adenda (o esta ve la baja).
        filas = self._filas(
            "SELECT archivado FROM paciente WHERE id_paciente = %s FOR UPDATE", (numero,)
        )
        if not filas:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if filas[0][0]:
            raise PacienteArchivado("El historial esta archivado; no admite cambios.")
        # FOR UPDATE: dos adendas a la misma consulta se aplican una tras otra.
        if not self._filas(
            "SELECT 1 FROM consulta_medica WHERE id_consulta = %s AND id_paciente = %s FOR UPDATE",
            (consulta, numero),
        ):
            raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")

        ahora = datetime.now(UTC)
        try:
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) FROM consulta_diagnostico WHERE id_consulta = %s", (consulta,)
                )
                previos = cursor.fetchone()[0]
                for posicion, d in enumerate(adenda.diagnosticos):
                    cursor.execute(
                        "INSERT INTO consulta_diagnostico (id_consulta, codigo, sistema_codigo, "
                        "descripcion, es_principal) VALUES (%s, %s, %s, %s, %s)",
                        (
                            consulta,
                            d.codigo,
                            d.sistema_codigo,
                            d.descripcion,
                            previos == 0 and posicion == 0,
                        ),
                    )
                for t in adenda.tratamientos:
                    cursor.execute(
                        "INSERT INTO consulta_tratamiento (id_consulta, descripcion) "
                        "VALUES (%s, %s)",
                        (consulta, t.descripcion),
                    )
                for r in adenda.recetas:
                    cursor.execute(
                        "INSERT INTO recetas_medicamento (id_consulta, medicamento, dosis, "
                        "frecuencia, duracion_dias, via_administracion, "
                        "instrucciones_adicionales, fecha_emitida) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            consulta,
                            r.medicamento,
                            r.dosis,
                            r.frecuencia,
                            r.duracion_dias,
                            r.via_administracion,
                            r.instrucciones,
                            utc_ingenuo(ahora),
                        ),
                    )
                # Las notas solo crecen por el final (lo exige tambien el trigger de la base).
                cursor.execute(
                    "UPDATE consulta_medica SET notas_medicas = "
                    "CONCAT_WS('\n\n', NULLIF(notas_medicas, ''), %s) WHERE id_consulta = %s",
                    (adenda.rotular(ahora, id_profesional), consulta),
                )
        except OperationalError as error:
            traducido = _traducir_trigger(error)
            if traducido is not None:
                raise traducido from error
            raise
        actualizada = self.obtener_consulta(id_paciente, id_consulta)
        assert actualizada is not None
        return actualizada

    def listar_consultas(
        self, id_paciente: str, limite: int, antes_de: datetime | None = None
    ) -> list[Consulta]:
        numero = entero_positivo(id_paciente)
        if numero is None:
            return []
        filtro, parametros = "", []
        if antes_de is not None:
            filtro = "AND c.fecha_hora < %s "
            parametros.append(utc_ingenuo(antes_de))
        return self._cargar(id_paciente, numero, filtro, parametros, limite)

    def _cargar(
        self, id_paciente: str, numero: int, filtro: str, extra: list[Any], limite: int
    ) -> list[Consulta]:
        parametros = [numero, *extra]
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


class RepositorioProfesionalesMySQL:
    def __init__(self, conexion: pymysql.Connection) -> None:
        self.conexion = conexion

    def obtener(self, id_profesional: str) -> ProfesionalLocal | None:
        try:
            uuid = str(UUID(id_profesional))
        except ValueError:
            return None
        with self.conexion.cursor() as cursor:
            cursor.execute(
                "SELECT id_profesional_central, nombre, apellido, activo FROM medico "
                "WHERE id_profesional_central = %s",
                (uuid,),
            )
            fila = cursor.fetchone()
        if fila is None:
            return None
        return ProfesionalLocal(fila[0], fila[1], fila[2], "medico", bool(fila[3]))

    def sincronizar(self, perfil: ProfesionalLocal) -> None:
        # El colegiado real lo completa el centro; mientras tanto uno provisional unico que
        # nunca se sobrescribe (igual que scripts/sincronizar_profesionales.py).
        uuid = str(UUID(perfil.id_profesional))
        with self.conexion.cursor() as cursor:
            cursor.execute(
                "INSERT INTO medico (id_profesional_central, nombre, apellido, colegiado, activo) "
                "VALUES (%s, %s, %s, %s, %s) AS nuevo "
                "ON DUPLICATE KEY UPDATE nombre = nuevo.nombre, apellido = nuevo.apellido, "
                "activo = nuevo.activo",
                (uuid, perfil.nombres, perfil.apellidos, f"PEND-{uuid}", perfil.activo),
            )


class RepositorioCitasMySQL:
    """Citas del centro. El trigger cita_validar_insert impide los choques de horario."""

    _SELECT = (
        "SELECT c.id_cita, c.id_paciente, CONCAT(p.nombre, ' ', p.apellido), "
        "COALESCE(m.id_profesional_central, CONCAT('sin-cuenta-', m.id_medico)), "
        "c.inicio, c.fin, c.motivo, c.estado, c.creada_por, c.motivo_cambio "
        "FROM cita c JOIN paciente p ON p.id_paciente = c.id_paciente "
        "JOIN medico m ON m.id_medico = c.id_medico "
    )

    def __init__(self, conexion: pymysql.Connection) -> None:
        self.conexion = conexion

    def _filas(self, sql: str, parametros: tuple | list = ()) -> tuple[tuple, ...]:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.fetchall()

    @staticmethod
    def _a_cita(fila: tuple) -> Cita:
        return Cita(
            id_cita=str(fila[0]),
            id_paciente=str(fila[1]),
            nombre_paciente=fila[2],
            id_profesional=fila[3],
            inicio=con_utc(fila[4]),
            fin=con_utc(fila[5]),
            motivo=fila[6],
            estado=EstadoCita(fila[7]),
            creada_por=fila[8],
            motivo_cambio=fila[9],
        )

    def obtener(self, id_cita: str) -> Cita | None:
        numero = entero_positivo(id_cita)
        if numero is None:
            return None
        filas = self._filas(self._SELECT + "WHERE c.id_cita = %s", (numero,))
        return self._a_cita(filas[0]) if filas else None

    def agendar(self, datos: NuevaCita, nombre_paciente: str, creada_por: str) -> Cita:
        paciente = entero_positivo(datos.id_paciente)
        if paciente is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        try:
            profesional, quien = str(UUID(datos.id_profesional)), str(UUID(creada_por))
        except ValueError as error:
            raise ProfesionalNoVinculado("La cuenta o el profesional no son validos.") from error
        filas = self._filas(
            "SELECT id_medico FROM medico WHERE id_profesional_central = %s", (profesional,)
        )
        if not filas:
            raise DatosInvalidos("El profesional no existe, no esta activo o no atiende.")
        try:
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO cita (id_paciente, id_medico, inicio, duracion_minutos, "
                    "motivo, creada_por) VALUES (%s, %s, %s, %s, %s, %s)",
                    (
                        paciente,
                        filas[0][0],
                        utc_ingenuo(datos.inicio),
                        datos.duracion_minutos,
                        datos.motivo,
                        quien,
                    ),
                )
                id_cita = cursor.lastrowid
        except OperationalError as error:
            traducido = _traducir_trigger(error)
            if traducido is not None:
                raise traducido from error
            raise
        cita = self.obtener(str(id_cita))
        assert cita is not None
        return cita

    def listar_agenda(
        self, desde: datetime, hasta: datetime, id_profesional: str | None = None
    ) -> list[Cita]:
        filtro, parametros = "", [utc_ingenuo(desde), utc_ingenuo(hasta)]
        if id_profesional is not None:
            try:
                parametros.append(str(UUID(id_profesional)))
            except ValueError:
                return []
            filtro = "AND m.id_profesional_central = %s "
        filas = self._filas(
            self._SELECT
            + "WHERE c.inicio >= %s AND c.inicio < %s "
            + filtro
            + "ORDER BY c.inicio, c.id_cita LIMIT 500",
            parametros,
        )
        return [self._a_cita(f) for f in filas]

    def listar_por_paciente(self, id_paciente: str, limite: int) -> list[Cita]:
        numero = entero_positivo(id_paciente)
        if numero is None:
            return []
        filas = self._filas(
            self._SELECT + "WHERE c.id_paciente = %s ORDER BY c.inicio DESC, c.id_cita DESC "
            "LIMIT %s",
            (numero, limite),
        )
        return [self._a_cita(f) for f in filas]

    def cambiar_estado(
        self, id_cita: str, estado: EstadoCita, por: str, motivo: str | None
    ) -> Cita:
        numero = entero_positivo(id_cita)
        if numero is None:
            raise CitaNoEncontrada("La cita no existe en tu institucion.")
        try:
            quien = str(UUID(por))
        except ValueError as error:
            raise ProfesionalNoVinculado("La cuenta no es valida.") from error
        # FOR UPDATE: dos cambios simultaneos sobre la misma cita se aplican uno tras otro.
        filas = self._filas("SELECT estado FROM cita WHERE id_cita = %s FOR UPDATE", (numero,))
        if not filas:
            raise CitaNoEncontrada("La cita no existe en tu institucion.")
        actual = EstadoCita(filas[0][0])
        if estado not in TRANSICIONES.get(actual, set()):
            raise ConflictoAgenda(f"Una cita '{actual}' no puede pasar a '{estado}'.")
        with self.conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE cita SET estado = %s, motivo_cambio = %s, actualizada_por = %s "
                "WHERE id_cita = %s",
                (estado.value, motivo, quien, numero),
            )
        cita = self.obtener(id_cita)
        assert cita is not None
        return cita


def _numero(valor: float | None) -> float | None:
    return None if valor is None else float(valor)


class RepositorioCrecimientoMySQL:
    """Controles de crecimiento (control_crecimiento): solo se agregan."""

    _SELECT = (
        "SELECT id_control, id_paciente_fk, fecha_registro, edad_meses, peso_kg, talla_cm, "
        "perimetro_cefalico, percentil_peso, percentil_talla, referencia_percentiles, "
        "observaciones FROM control_crecimiento "
    )

    def __init__(self, conexion: pymysql.Connection) -> None:
        self.conexion = conexion

    def _filas(self, sql: str, parametros: tuple = ()) -> tuple[tuple, ...]:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.fetchall()

    @staticmethod
    def _a_control(fila: tuple) -> ControlCrecimiento:
        return ControlCrecimiento(
            str(fila[0]),
            str(fila[1]),
            con_utc(fila[2]),
            fila[3],
            _numero(fila[4]),
            _numero(fila[5]),
            _numero(fila[6]),
            _numero(fila[7]),
            _numero(fila[8]),
            fila[9],
            fila[10],
        )

    def registrar(
        self, id_paciente: str, datos: NuevoControl, fecha: datetime, edad_meses: int | None
    ) -> ControlCrecimiento:
        numero = entero_positivo(id_paciente)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        try:
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO control_crecimiento (id_paciente_fk, fecha_registro, edad_meses, "
                    "peso_kg, talla_cm, perimetro_cefalico, percentil_peso, percentil_talla, "
                    "referencia_percentiles, observaciones) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        numero,
                        utc_ingenuo(fecha),
                        edad_meses,
                        datos.peso_kg,
                        datos.talla_cm,
                        datos.perimetro_cefalico,
                        datos.percentil_peso,
                        datos.percentil_talla,
                        datos.referencia_percentiles,
                        datos.observaciones,
                    ),
                )
                nuevo = cursor.lastrowid
        except OperationalError as error:
            traducido = _traducir_trigger(error)
            if traducido is not None:
                raise traducido from error
            if error.args and error.args[0] == ER_CHECK_VIOLATED:
                raise DatosInvalidos("Las medidas no cumplen los rangos permitidos.") from error
            raise
        except IntegrityError as error:
            if error.args and error.args[0] == ER_NO_REFERENCED_ROW:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.") from error
            raise
        fila = self._filas(self._SELECT + "WHERE id_control = %s", (nuevo,))[0]
        return self._a_control(fila)

    def listar(self, id_paciente: str, limite: int) -> list[ControlCrecimiento]:
        numero = entero_positivo(id_paciente)
        if numero is None:
            return []
        filas = self._filas(
            self._SELECT
            + "WHERE id_paciente_fk = %s ORDER BY fecha_registro DESC, id_control DESC LIMIT %s",
            (numero, limite),
        )
        return [self._a_control(f) for f in filas]


ESTADO_DOSIS_BD = {
    "Pendiente": EstadoDosis.PENDIENTE,
    "Aplicada": EstadoDosis.APLICADA,
    "Cancelada": EstadoDosis.CANCELADA,
}


class RepositorioVacunacionMySQL:
    """Esquema de vacunacion y catalogo de tipos de vacuna (nombre_vacuna).

    El administrador del centro agrega vacunas y corrige su descripcion (019); el nombre no
    cambia ni se borra una vacuna, porque los esquemas ya apuntan a ella.

    Decision del equipo: no se controlan lotes ni existencias (migracion 010). Aplicar una
    dosis solo registra quien, cuando y las observaciones.
    """

    _DOSIS = (
        "SELECT e.id_esquema, e.id_paciente_fk, e.id_nombre_vacuna_fk, n.nombre, "
        "e.estado_aplicacion, e.numero_dosis, e.fecha_programada, e.fecha_aplicacion, "
        "m.id_profesional_central, e.observaciones_reaccion "
        "FROM esquema_vacunacion e "
        "JOIN nombre_vacuna n ON n.id_nombre_vacuna = e.id_nombre_vacuna_fk "
        "LEFT JOIN medico m ON m.id_medico = e.id_medico_aplicador "
    )

    def __init__(self, conexion: pymysql.Connection) -> None:
        self.conexion = conexion

    def _filas(self, sql: str, parametros: tuple = ()) -> tuple[tuple, ...]:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.fetchall()

    @staticmethod
    def _a_dosis(fila: tuple) -> DosisVacuna:
        return DosisVacuna(
            id_dosis=str(fila[0]),
            id_paciente=str(fila[1]),
            id_vacuna=str(fila[2]),
            nombre_vacuna=fila[3],
            estado=ESTADO_DOSIS_BD[fila[4]],
            numero_dosis=fila[5],
            fecha_programada=fila[6],
            fecha_aplicacion=con_utc(fila[7]) if fila[7] else None,
            id_aplicador=fila[8],
            observaciones_reaccion=fila[9],
        )

    _TIPOS = (
        "SELECT id_nombre_vacuna, nombre, enfermedades_que_previene, edad_recomendada_meses, "
        "dosis_sugerida FROM nombre_vacuna "
    )

    def listar_tipos(self) -> list[TipoVacuna]:
        filas = self._filas(
            self._TIPOS + "ORDER BY edad_recomendada_meses IS NULL, edad_recomendada_meses, nombre"
        )
        return [TipoVacuna(str(f[0]), f[1], f[2], f[3], f[4]) for f in filas]

    def _tipo(self, numero: int) -> TipoVacuna | None:
        filas = self._filas(self._TIPOS + "WHERE id_nombre_vacuna = %s", (numero,))
        return TipoVacuna(str(filas[0][0]), *filas[0][1:]) if filas else None

    def agregar_tipo(self, nombre: str, descripcion: DescripcionVacuna) -> TipoVacuna:
        try:
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO nombre_vacuna (nombre, enfermedades_que_previene, "
                    "edad_recomendada_meses, dosis_sugerida) VALUES (%s, %s, %s, %s)",
                    (
                        nombre,
                        descripcion.enfermedades_que_previene,
                        descripcion.edad_recomendada_meses,
                        descripcion.dosis_sugerida,
                    ),
                )
                numero = cursor.lastrowid
        except IntegrityError as error:
            if error.args and error.args[0] == ER_DUP_ENTRY:
                raise ConflictoEstado("Ya existe una vacuna con ese nombre.") from error
            raise
        tipo = self._tipo(numero)
        assert tipo is not None
        return tipo

    def describir_tipo(self, id_vacuna: str, descripcion: DescripcionVacuna) -> TipoVacuna:
        numero = entero_positivo(id_vacuna)
        if numero is None or self._tipo(numero) is None:
            raise RegistroNoEncontrado("La vacuna no existe en el catalogo.")
        with self.conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE nombre_vacuna SET enfermedades_que_previene = %s, "
                "edad_recomendada_meses = %s, dosis_sugerida = %s WHERE id_nombre_vacuna = %s",
                (
                    descripcion.enfermedades_que_previene,
                    descripcion.edad_recomendada_meses,
                    descripcion.dosis_sugerida,
                    numero,
                ),
            )
        tipo = self._tipo(numero)
        assert tipo is not None
        return tipo

    def listar_esquema(self, id_paciente: str) -> list[DosisVacuna]:
        numero = entero_positivo(id_paciente)
        if numero is None:
            return []
        filas = self._filas(
            self._DOSIS + "WHERE e.id_paciente_fk = %s "
            "ORDER BY e.fecha_programada IS NULL, e.fecha_programada, e.id_esquema",
            (numero,),
        )
        return [self._a_dosis(f) for f in filas]

    def obtener_dosis(self, id_paciente: str, id_dosis: str) -> DosisVacuna | None:
        paciente, dosis = entero_positivo(id_paciente), entero_positivo(id_dosis)
        if paciente is None or dosis is None:
            return None
        filas = self._filas(
            self._DOSIS + "WHERE e.id_paciente_fk = %s AND e.id_esquema = %s", (paciente, dosis)
        )
        return self._a_dosis(filas[0]) if filas else None

    def programar(
        self,
        id_paciente: str,
        id_vacuna: str,
        numero_dosis: int | None,
        fecha_programada: date | None,
    ) -> DosisVacuna:
        paciente, vacuna = entero_positivo(id_paciente), entero_positivo(id_vacuna)
        if paciente is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if vacuna is None:
            raise DatosInvalidos("La vacuna no existe en el catalogo.")
        try:
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO esquema_vacunacion (id_paciente_fk, id_nombre_vacuna_fk, "
                    "numero_dosis, fecha_programada, estado_aplicacion) "
                    "VALUES (%s, %s, %s, %s, 'Pendiente')",
                    (paciente, vacuna, numero_dosis, fecha_programada),
                )
                nuevo = cursor.lastrowid
        except OperationalError as error:
            traducido = _traducir_trigger(error)
            if traducido is not None:
                raise traducido from error
            raise
        except IntegrityError as error:
            if error.args and error.args[0] == ER_NO_REFERENCED_ROW:
                raise DatosInvalidos("La vacuna no existe en el catalogo.") from error
            raise
        dosis = self.obtener_dosis(id_paciente, str(nuevo))
        assert dosis is not None
        return dosis

    def aplicar(
        self,
        id_paciente: str,
        id_dosis: str,
        id_profesional: str,
        fecha: datetime,
        observaciones: str | None,
    ) -> DosisVacuna:
        paciente, numero = entero_positivo(id_paciente), entero_positivo(id_dosis)
        if paciente is None or numero is None:
            raise RegistroNoEncontrado("La dosis no existe en el esquema del paciente.")
        id_medico = _id_medico_activo(self._filas, id_profesional)
        # Bloquea la dosis: dos aplicaciones simultaneas de la misma dosis van una tras otra.
        filas = self._filas(
            "SELECT estado_aplicacion FROM esquema_vacunacion "
            "WHERE id_esquema = %s AND id_paciente_fk = %s FOR UPDATE",
            (numero, paciente),
        )
        if not filas:
            raise RegistroNoEncontrado("La dosis no existe en el esquema del paciente.")
        if filas[0][0] != "Pendiente":
            raise ConflictoEstado(
                f"Una dosis {ESTADO_DOSIS_BD[filas[0][0]].value} no puede aplicarse."
            )
        try:
            with self.conexion.cursor() as cursor:
                cursor.execute(
                    "UPDATE esquema_vacunacion SET estado_aplicacion = 'Aplicada', "
                    "fecha_aplicacion = %s, id_medico_aplicador = %s, "
                    "observaciones_reaccion = %s WHERE id_esquema = %s",
                    (utc_ingenuo(fecha), id_medico, observaciones, numero),
                )
        except OperationalError as error:
            traducido = _traducir_trigger(error)
            if traducido is not None:
                raise traducido from error
            raise
        dosis = self.obtener_dosis(id_paciente, id_dosis)
        assert dosis is not None
        return dosis

    def cancelar(self, id_paciente: str, id_dosis: str) -> DosisVacuna:
        paciente, numero = entero_positivo(id_paciente), entero_positivo(id_dosis)
        if paciente is None or numero is None:
            raise RegistroNoEncontrado("La dosis no existe en el esquema del paciente.")
        filas = self._filas(
            "SELECT estado_aplicacion FROM esquema_vacunacion "
            "WHERE id_esquema = %s AND id_paciente_fk = %s FOR UPDATE",
            (numero, paciente),
        )
        if not filas:
            raise RegistroNoEncontrado("La dosis no existe en el esquema del paciente.")
        if filas[0][0] != "Pendiente":
            raise ConflictoEstado(
                f"Una dosis {ESTADO_DOSIS_BD[filas[0][0]].value} no puede cancelarse."
            )
        with self.conexion.cursor() as cursor:
            cursor.execute(
                "UPDATE esquema_vacunacion SET estado_aplicacion = 'Cancelada' "
                "WHERE id_esquema = %s",
                (numero,),
            )
        dosis = self.obtener_dosis(id_paciente, id_dosis)
        assert dosis is not None
        return dosis


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
        self.profesionales = RepositorioProfesionalesMySQL(self.conexion)
        self.citas = RepositorioCitasMySQL(self.conexion)
        self.crecimiento = RepositorioCrecimientoMySQL(self.conexion)
        self.vacunacion = RepositorioVacunacionMySQL(self.conexion)
        # El odontograma es propio de la clinica odontologica (HTTP 501 aqui).
        pendientes = repositorios_pendientes(MOTOR)
        self.odontograma = pendientes["odontograma"]
        self.laboratorio = pendientes["laboratorio"]
        self.hospital = pendientes["hospital"]
        self.cobros = RepositorioCobrosMySQL(self.conexion)
        self.tutores = RepositorioTutoresMySQL(self.conexion)
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

    def resumen_operativo(self, desde: datetime, hasta: datetime) -> dict:
        with self.conexion.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM paciente")
            pacientes = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM cita WHERE inicio >= %s AND inicio < %s",
                (utc_ingenuo(desde), utc_ingenuo(hasta)),
            )
            citas = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*), COALESCE(sum(total_facturado - total_pagado),0) "
                "FROM facturacion WHERE anulada_en IS NULL "
                "AND (total_facturado = 0 OR total_pagado < total_facturado)"
            )
            abiertos, saldo = cursor.fetchone()
        return {
            "pacientes_registrados": pacientes,
            "citas_hoy": citas,
            "cobros_abiertos": abiertos,
            "saldo_pendiente": saldo,
        }
