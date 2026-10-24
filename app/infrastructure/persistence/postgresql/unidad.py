"""Hospital General (PostgreSQL): registrar paciente, historial, consultas, archivo y busqueda.

Una solicitud = una conexion = una transaccion. Todo lo que escribe un caso de uso
(por ejemplo atencion + diagnosticos + tratamientos + receta) se confirma junto en
commit() o no se guarda. El modelo original separa lo que el contrato comun
llama "consulta" en varias tablas:

    consulta  -> atencion (tipo CONSULTA)
    diagnosticos -> diagnostico (hijas de la atencion)
    tratamientos -> tratamiento (hijas de un DIAGNOSTICO)
    recetas   -> orden_medica -> receta -> detalle_receta
"""

from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Literal, Self
from uuid import UUID

import psycopg

from app.application.errores import IntegracionNoConfigurada
from app.domain.consulta import Consulta, Diagnostico, NuevaConsulta, Receta, Tratamiento
from app.domain.errores import (
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
)
from app.domain.paciente import Alergia, Baja, Contacto, NuevoPaciente, Paciente
from app.infrastructure.persistence.pendiente import repositorios_pendientes

MOTOR = "PostgreSQL"
ESTADO_ARCHIVADO = "Inactivo"


def _entero(id_paciente: str) -> int | None:
    """Los identificadores son enteros positivos de 32 bits; todo lo demas no existe."""
    if not id_paciente.isascii() or not id_paciente.isdecimal():
        return None
    numero = int(id_paciente)
    return numero if 0 < numero <= 2_147_483_647 else None


def _escapar_like(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _utc_ingenuo(valor: datetime) -> datetime:
    """Las columnas TIMESTAMP guardan UTC sin zona; asi no dependen de la zona del servidor."""
    if valor.tzinfo is None:
        return valor
    return valor.astimezone(UTC).replace(tzinfo=None)


def _con_utc(valor: datetime) -> datetime:
    return valor.replace(tzinfo=UTC) if valor.tzinfo is None else valor.astimezone(UTC)


class RepositorioPacientesPostgreSQL:
    def __init__(self, conexion: psycopg.Connection) -> None:
        self.conexion = conexion

    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        numero = _entero(id_paciente)
        if numero is None:
            return None
        fila = self.conexion.execute(
            "SELECT id_paciente, nombres, apellidos, fecha_nacimiento, estado, telefono, "
            "correo_electronico, direccion, alergias_evaluadas "
            "FROM paciente WHERE id_paciente = %s",
            (numero,),
        ).fetchone()
        if fila is None:
            return None
        telefono, correo, direccion = fila[5], fila[6], fila[7]
        alergias = None
        if fila[8]:
            alergias = tuple(
                Alergia(sustancia, reaccion, severidad)
                for sustancia, reaccion, severidad in self.conexion.execute(
                    "SELECT sustancia, reaccion, severidad FROM paciente_alergia "
                    "WHERE id_paciente = %s ORDER BY sustancia",
                    (numero,),
                )
            )
        return Paciente(
            str(fila[0]),
            fila[1],
            fila[2],
            fila[3],
            archivado=fila[4] == ESTADO_ARCHIVADO,
            contacto=Contacto(telefono, correo, direccion)
            if telefono or correo or direccion
            else None,
            alergias=alergias,
        )

    def registrar(self, datos: NuevoPaciente) -> Paciente:
        contacto = datos.contacto or Contacto()
        id_nuevo = self.conexion.execute(
            "INSERT INTO paciente (nombres, apellidos, fecha_nacimiento, telefono, "
            "correo_electronico, direccion, alergias_evaluadas) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id_paciente",
            (
                datos.nombres,
                datos.apellidos,
                datos.fecha_nacimiento,
                contacto.telefono,
                contacto.correo,
                contacto.direccion,
                datos.alergias is not None,
            ),
        ).fetchone()[0]
        for a in datos.alergias or ():
            self.conexion.execute(
                "INSERT INTO paciente_alergia (id_paciente, sustancia, reaccion, severidad) "
                "VALUES (%s, %s, %s, %s)",
                (id_nuevo, a.sustancia, a.reaccion, a.severidad),
            )
        return Paciente(
            str(id_nuevo),
            datos.nombres,
            datos.apellidos,
            datos.fecha_nacimiento,
            contacto=datos.contacto,
            alergias=datos.alergias,
        )

    def buscar(self, palabras: tuple[str, ...], limite: int) -> list[Paciente]:
        # Regla comun (domain/busqueda.py): cada palabra es el comienzo de alguna palabra
        # del nombre, sin mayusculas ni acentos. unaccent() requiere la migracion 008.
        condiciones = []
        parametros: list[Any] = []
        for palabra in palabras:
            condiciones.append("(nombre_norm LIKE %s OR nombre_norm LIKE %s)")
            parametros += [f"{_escapar_like(palabra)}%", f"% {_escapar_like(palabra)}%"]
        filas = self.conexion.execute(
            "SELECT id_paciente, nombres, apellidos, fecha_nacimiento, estado FROM ("
            "  SELECT *, lower(unaccent(nombres || ' ' || apellidos)) AS nombre_norm FROM paciente"
            ") p WHERE " + " AND ".join(condiciones) + " "
            "ORDER BY lower(unaccent(apellidos)), lower(unaccent(nombres)), id_paciente "
            "LIMIT %s",
            (*parametros, limite),
        ).fetchall()
        return [
            Paciente(str(f[0]), f[1], f[2], f[3], archivado=f[4] == ESTADO_ARCHIVADO) for f in filas
        ]

    def archivar(self, id_paciente: str, baja: Baja) -> None:
        numero = _entero(id_paciente)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        # Condicional: si otra solicitud lo archivo primero, no se sobrescribe su baja.
        try:
            cambiados = self.conexion.execute(
                "UPDATE paciente SET estado = %s, fecha_baja = %s, motivo_baja = %s, "
                "detalle_baja = %s, archivado_por = %s "
                "WHERE id_paciente = %s AND estado = 'Activo'",
                (
                    ESTADO_ARCHIVADO,
                    baja.fecha.astimezone(UTC).date(),
                    baja.motivo.value,
                    baja.detalle,
                    UUID(baja.id_profesional),
                    numero,
                ),
            ).rowcount
        except ValueError as error:  # id_profesional no es un UUID
            raise ProfesionalNoVinculado("La cuenta no es valida para dar de baja.") from error
        if cambiados == 0:
            existe = self.conexion.execute(
                "SELECT 1 FROM paciente WHERE id_paciente = %s", (numero,)
            ).fetchone()
            if existe is None:
                raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
            raise PacienteArchivado("El historial ya estaba archivado.")


class RepositorioHistorialPostgreSQL:
    def __init__(self, conexion: psycopg.Connection) -> None:
        self.conexion = conexion

    def _id_personal(self, id_profesional: str) -> int:
        try:
            uuid = UUID(id_profesional)
        except ValueError as error:
            raise ProfesionalNoVinculado(
                "Tu cuenta no es un profesional de este hospital."
            ) from error
        fila = self.conexion.execute(
            "SELECT id_personal FROM personal_medico "
            "WHERE id_profesional_central = %s AND estado = 'Activo'",
            (uuid,),
        ).fetchone()
        if fila is None:
            raise ProfesionalNoVinculado(
                "Tu cuenta no esta vinculada a personal activo del Hospital General. "
                "Pide que ejecuten: python -m scripts.sincronizar_profesionales"
            )
        return fila[0]

    def registrar_consulta(
        self, id_paciente: str, id_profesional: str, datos: NuevaConsulta
    ) -> Consulta:
        numero = _entero(id_paciente)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if datos.tratamientos and not datos.diagnosticos:
            # En el modelo del hospital un tratamiento cuelga de un diagnostico.
            raise DatosInvalidos(
                "En el Hospital General cada tratamiento se registra bajo un diagnostico: "
                "agrega al menos un diagnostico."
            )
        id_personal = self._id_personal(id_profesional)
        # Bloquea la fila del paciente mientras dura la transaccion: una baja concurrente
        # espera a que esta consulta termine (o la consulta ve la baja y se rechaza).
        estado = self.conexion.execute(
            "SELECT estado FROM paciente WHERE id_paciente = %s FOR SHARE", (numero,)
        ).fetchone()
        if estado is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if estado[0] == ESTADO_ARCHIVADO:
            raise PacienteArchivado("El historial esta archivado; no admite consultas nuevas.")

        ahora = datetime.now(UTC)
        try:
            id_atencion = self.conexion.execute(
                "INSERT INTO atencion (id_paciente, id_personal, tipo_atencion, fecha_hora, "
                "motivo, notas) VALUES (%s, %s, 'CONSULTA', %s, %s, %s) RETURNING id_atencion",
                (numero, id_personal, _utc_ingenuo(ahora), datos.motivo, datos.notas),
            ).fetchone()[0]
        except psycopg.errors.CheckViolation as error:
            # Respaldo de la regla en la base (trg_atencion_paciente_activo).
            raise PacienteArchivado(
                "El historial esta archivado; no admite consultas nuevas."
            ) from error

        ids_diagnostico = []
        for d in datos.diagnosticos:
            ids_diagnostico.append(
                self.conexion.execute(
                    "INSERT INTO diagnostico (id_atencion, descripcion, codigo, sistema_codigo) "
                    "VALUES (%s, %s, %s, %s) RETURNING id_diagnostico",
                    (id_atencion, d.descripcion, d.codigo, d.sistema_codigo),
                ).fetchone()[0]
            )
        for t in datos.tratamientos:
            # El contrato comun no distingue a que diagnostico pertenece cada tratamiento:
            # se guardan bajo el primero.
            self.conexion.execute(
                "INSERT INTO tratamiento (id_diagnostico, descripciones) VALUES (%s, %s)",
                (ids_diagnostico[0], t.descripcion),
            )
        if datos.recetas:
            id_orden = self.conexion.execute(
                "INSERT INTO orden_medica (id_atencion, id_personal, fecha_hora, tipo_orden) "
                "VALUES (%s, %s, %s, 'Medicamento') RETURNING id_orden",
                (id_atencion, id_personal, _utc_ingenuo(ahora)),
            ).fetchone()[0]
            id_receta = self.conexion.execute(
                "INSERT INTO receta (id_orden, fecha_hora) VALUES (%s, %s) RETURNING id_receta",
                (id_orden, _utc_ingenuo(ahora)),
            ).fetchone()[0]
            for r in datos.recetas:
                self.conexion.execute(
                    "INSERT INTO detalle_receta (id_receta, medicamento, dosis, frecuencia, "
                    "via_administracion, duracion_dias, indicaciones) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        id_receta,
                        r.medicamento,
                        r.dosis,
                        r.frecuencia,
                        r.via_administracion,
                        r.duracion_dias,
                        r.instrucciones,
                    ),
                )
        return Consulta(
            str(id_atencion),
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
        numero = _entero(id_paciente)
        if numero is None:
            return []
        filtro, parametros = "", [numero]
        if antes_de is not None:
            filtro = "AND a.fecha_hora < %s "
            parametros.append(_utc_ingenuo(antes_de))
        filas = self.conexion.execute(
            "SELECT a.id_atencion, COALESCE(pm.id_profesional_central::text, "
            "'sin-cuenta-' || pm.id_personal), a.fecha_hora, "
            "COALESCE(a.motivo, a.detalle, '(sin motivo registrado)'), a.notas "
            "FROM atencion a JOIN personal_medico pm ON pm.id_personal = a.id_personal "
            "WHERE a.id_paciente = %s AND a.tipo_atencion = 'CONSULTA' "
            + filtro
            + "ORDER BY a.fecha_hora DESC, a.id_atencion DESC LIMIT %s",
            (*parametros, limite),
        ).fetchall()
        if not filas:
            return []
        ids = [f[0] for f in filas]
        diagnosticos: dict[int, list[Diagnostico]] = {i: [] for i in ids}
        tratamientos: dict[int, list[Tratamiento]] = {i: [] for i in ids}
        recetas: dict[int, list[Receta]] = {i: [] for i in ids}
        for id_atencion, descripcion, codigo, sistema in self.conexion.execute(
            "SELECT id_atencion, descripcion, codigo, sistema_codigo FROM diagnostico "
            "WHERE id_atencion = ANY(%s) ORDER BY id_diagnostico",
            (ids,),
        ):
            diagnosticos[id_atencion].append(Diagnostico(descripcion, codigo, sistema))
        for id_atencion, descripcion in self.conexion.execute(
            "SELECT d.id_atencion, t.descripciones FROM tratamiento t "
            "JOIN diagnostico d ON d.id_diagnostico = t.id_diagnostico "
            "WHERE d.id_atencion = ANY(%s) ORDER BY t.id_tratamiento",
            (ids,),
        ):
            tratamientos[id_atencion].append(Tratamiento(descripcion or ""))
        for fila in self.conexion.execute(
            "SELECT o.id_atencion, dr.medicamento, dr.dosis, dr.frecuencia, "
            "dr.via_administracion, dr.duracion_dias, dr.indicaciones "
            "FROM detalle_receta dr JOIN receta r ON r.id_receta = dr.id_receta "
            "JOIN orden_medica o ON o.id_orden = r.id_orden "
            "WHERE o.id_atencion = ANY(%s) ORDER BY dr.id_detalle",
            (ids,),
        ):
            recetas[fila[0]].append(
                Receta(fila[1], fila[2] or "", fila[3] or "", fila[4], fila[5], fila[6])
            )
        return [
            Consulta(
                str(f[0]),
                id_paciente,
                f[1],
                _con_utc(f[2]),
                f[3],
                f[4],
                tuple(diagnosticos[f[0]]),
                tuple(tratamientos[f[0]]),
                tuple(recetas[f[0]]),
            )
            for f in filas
        ]


class UnidadTrabajoPostgreSQL:
    """Cada solicitud abre su conexion y la cierra; sin commit() todo se revierte."""

    def __init__(
        self,
        dsn: str,
        conectar: Callable[[], psycopg.Connection] | None = None,
    ) -> None:
        self.dsn = dsn
        self._conectar = conectar or self._conectar_por_defecto
        self.conexion: psycopg.Connection | None = None

    def _conectar_por_defecto(self) -> psycopg.Connection:
        return psycopg.connect(self.dsn, connect_timeout=5, options="-c statement_timeout=10000")

    def __enter__(self) -> Self:
        try:
            self.conexion = self._conectar()
        except psycopg.Error as error:
            raise IntegracionNoConfigurada("La base clinica no esta disponible.") from error
        self.pacientes = RepositorioPacientesPostgreSQL(self.conexion)
        self.historial = RepositorioHistorialPostgreSQL(self.conexion)
        # Citas, perfiles y odontograma: pendientes en este motor (HTTP 501).
        for nombre, repositorio in repositorios_pendientes(MOTOR).items():
            if nombre not in ("historial",):
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
        if isinstance(exc_value, psycopg.Error):
            # Errores de base no previstos por el adaptador: sin detalles hacia el cliente.
            raise IntegracionNoConfigurada("La consulta clinica no esta disponible.") from exc_value
        return False

    def commit(self) -> None:
        self.conexion.commit()

    def rollback(self) -> None:
        self.conexion.rollback()
