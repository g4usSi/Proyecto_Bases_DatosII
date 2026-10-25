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
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

import psycopg

from app.application.errores import IntegracionNoConfigurada
from app.domain.cita import TRANSICIONES, Cita, EstadoCita, NuevaCita
from app.domain.consulta import Adenda, Consulta, Diagnostico, NuevaConsulta, Receta, Tratamiento
from app.domain.errores import (
    CitaNoEncontrada,
    ConflictoAgenda,
    ConsultaNoEncontrada,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
)
from app.domain.paciente import Alergia, Baja, CambiosPaciente, Contacto, NuevoPaciente, Paciente
from app.domain.profesional import ProfesionalLocal
from app.infrastructure.persistence.comun import (
    con_utc,
    entero_positivo,
    escapar_like,
    utc_ingenuo,
)
from app.infrastructure.persistence.pendiente import repositorios_pendientes
from app.infrastructure.persistence.postgresql.cobros import RepositorioCobrosPostgreSQL
from app.infrastructure.persistence.postgresql.hospital import RepositorioHospitalPostgreSQL

MOTOR = "PostgreSQL"
ESTADO_ARCHIVADO = "Inactivo"
# La tabla cita guarda el estado con la capitalizacion del modelo original.
ESTADO_CITA_BD = {
    EstadoCita.PROGRAMADA: "Programada",
    EstadoCita.CONFIRMADA: "Confirmada",
    EstadoCita.ATENDIDA: "Atendida",
    EstadoCita.CANCELADA: "Cancelada",
    EstadoCita.NO_ASISTIO: "No_asistio",
}
ESTADO_CITA_DOMINIO = {valor: clave for clave, valor in ESTADO_CITA_BD.items()}
# Rol de la identidad central -> rol del modelo original (personal_medico.rol).
ROL_PERSONAL_MEDICO = {
    "medico": "Medico",
    "enfermeria": "Enfermero",
    "laboratorista": "Tecnico",
    "odontologo": "Medico",
}


class RepositorioPacientesPostgreSQL:
    def __init__(self, conexion: psycopg.Connection) -> None:
        self.conexion = conexion

    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        numero = entero_positivo(id_paciente)
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
            parametros += [f"{escapar_like(palabra)}%", f"% {escapar_like(palabra)}%"]
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
        numero = entero_positivo(id_paciente)
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

    def actualizar(self, id_paciente: str, cambios: CambiosPaciente) -> None:
        numero = entero_positivo(id_paciente)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        asignaciones, parametros = [], []
        for columna, valor in (
            ("nombres", cambios.nombres),
            ("apellidos", cambios.apellidos),
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
            cambiados = self.conexion.execute(
                "UPDATE paciente SET " + ", ".join(asignaciones) + " "
                "WHERE id_paciente = %s AND estado = 'Activo'",
                (*parametros, numero),
            ).rowcount
        except psycopg.errors.CheckViolation as error:
            raise DatosInvalidos("La fecha de nacimiento no puede ser futura.") from error
        self._comprobar_activo(numero, cambiados)

    def agregar_alergias(self, id_paciente: str, alergias: tuple[Alergia, ...]) -> None:
        numero = entero_positivo(id_paciente)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        # Condicional: tambien marca el historial como "alergias evaluadas".
        cambiados = self.conexion.execute(
            "UPDATE paciente SET alergias_evaluadas = TRUE "
            "WHERE id_paciente = %s AND estado = 'Activo'",
            (numero,),
        ).rowcount
        self._comprobar_activo(numero, cambiados)
        try:
            for a in alergias:
                self.conexion.execute(
                    "INSERT INTO paciente_alergia (id_paciente, sustancia, reaccion, severidad) "
                    "VALUES (%s, %s, %s, %s)",
                    (numero, a.sustancia, a.reaccion, a.severidad),
                )
        except psycopg.errors.UniqueViolation as error:
            raise DatosInvalidos("Esa alergia ya estaba registrada.") from error

    def _comprobar_activo(self, numero: int, cambiados: int) -> None:
        """Tras un UPDATE condicional (estado = 'Activo'): distingue ausente de archivado."""
        if cambiados:
            return
        existe = self.conexion.execute(
            "SELECT 1 FROM paciente WHERE id_paciente = %s", (numero,)
        ).fetchone()
        if existe is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        raise PacienteArchivado("El historial esta archivado; no admite cambios.")


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
        numero = entero_positivo(id_paciente)
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
                (numero, id_personal, utc_ingenuo(ahora), datos.motivo, datos.notas),
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
        self._insertar_recetas(id_atencion, id_personal, ahora, datos.recetas)
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

    def _insertar_recetas(
        self, id_atencion: int, id_personal: int, ahora: datetime, recetas: tuple[Receta, ...]
    ) -> None:
        if not recetas:
            return
        id_orden = self.conexion.execute(
            "INSERT INTO orden_medica (id_atencion, id_personal, fecha_hora, tipo_orden) "
            "VALUES (%s, %s, %s, 'Medicamento') RETURNING id_orden",
            (id_atencion, id_personal, utc_ingenuo(ahora)),
        ).fetchone()[0]
        id_receta = self.conexion.execute(
            "INSERT INTO receta (id_orden, fecha_hora) VALUES (%s, %s) RETURNING id_receta",
            (id_orden, utc_ingenuo(ahora)),
        ).fetchone()[0]
        for r in recetas:
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

    def obtener_consulta(self, id_paciente: str, id_consulta: str) -> Consulta | None:
        numero, atencion = entero_positivo(id_paciente), entero_positivo(id_consulta)
        if numero is None or atencion is None:
            return None
        consultas = self._cargar(id_paciente, numero, "AND a.id_atencion = %s ", [atencion], 1)
        return consultas[0] if consultas else None

    def agregar_a_consulta(
        self, id_paciente: str, id_consulta: str, id_profesional: str, adenda: Adenda
    ) -> Consulta:
        numero, atencion = entero_positivo(id_paciente), entero_positivo(id_consulta)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if atencion is None:
            raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")
        id_personal = self._id_personal(id_profesional)
        # Una baja concurrente espera a que termine esta adenda (o esta ve la baja).
        estado = self.conexion.execute(
            "SELECT estado FROM paciente WHERE id_paciente = %s FOR SHARE", (numero,)
        ).fetchone()
        if estado is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if estado[0] == ESTADO_ARCHIVADO:
            raise PacienteArchivado("El historial esta archivado; no admite cambios.")
        # FOR UPDATE: dos adendas a la misma consulta se aplican una tras otra.
        existe = self.conexion.execute(
            "SELECT 1 FROM atencion WHERE id_atencion = %s AND id_paciente = %s "
            "AND tipo_atencion = 'CONSULTA' FOR UPDATE",
            (atencion, numero),
        ).fetchone()
        if existe is None:
            raise ConsultaNoEncontrada("La consulta no existe en el historial del paciente.")

        ahora = datetime.now(UTC)
        try:
            ids_diagnostico = [
                self.conexion.execute(
                    "INSERT INTO diagnostico (id_atencion, descripcion, codigo, sistema_codigo) "
                    "VALUES (%s, %s, %s, %s) RETURNING id_diagnostico",
                    (atencion, d.descripcion, d.codigo, d.sistema_codigo),
                ).fetchone()[0]
                for d in adenda.diagnosticos
            ]
            if adenda.tratamientos:
                destino = ids_diagnostico[0] if ids_diagnostico else None
                if destino is None:
                    # En este modelo un tratamiento cuelga de un diagnostico ya existente.
                    fila = self.conexion.execute(
                        "SELECT id_diagnostico FROM diagnostico WHERE id_atencion = %s "
                        "ORDER BY id_diagnostico LIMIT 1",
                        (atencion,),
                    ).fetchone()
                    if fila is None:
                        raise DatosInvalidos(
                            "En el Hospital General cada tratamiento se registra bajo un "
                            "diagnostico: agrega tambien un diagnostico."
                        )
                    destino = fila[0]
                for t in adenda.tratamientos:
                    self.conexion.execute(
                        "INSERT INTO tratamiento (id_diagnostico, descripciones) VALUES (%s, %s)",
                        (destino, t.descripcion),
                    )
            self._insertar_recetas(atencion, id_personal, ahora, adenda.recetas)
            # Las notas solo crecen por el final (lo exige tambien el trigger de la base).
            rotulo = adenda.rotular(ahora, id_profesional)
            self.conexion.execute(
                "UPDATE atencion SET notas = CASE WHEN COALESCE(notas, '') = '' THEN %s "
                "ELSE notas || E'\n\n' || %s END WHERE id_atencion = %s",
                (rotulo, rotulo, atencion),
            )
        except psycopg.errors.CheckViolation as error:
            raise PacienteArchivado("El historial esta archivado; no admite cambios.") from error
        consulta = self.obtener_consulta(id_paciente, id_consulta)
        assert consulta is not None
        return consulta

    def listar_consultas(
        self, id_paciente: str, limite: int, antes_de: datetime | None = None
    ) -> list[Consulta]:
        numero = entero_positivo(id_paciente)
        if numero is None:
            return []
        filtro, parametros = "", []
        if antes_de is not None:
            filtro = "AND a.fecha_hora < %s "
            parametros.append(utc_ingenuo(antes_de))
        return self._cargar(id_paciente, numero, filtro, parametros, limite)

    def _cargar(
        self, id_paciente: str, numero: int, filtro: str, extra: list[Any], limite: int
    ) -> list[Consulta]:
        parametros = [numero, *extra]
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
                con_utc(f[2]),
                f[3],
                f[4],
                tuple(diagnosticos[f[0]]),
                tuple(tratamientos[f[0]]),
                tuple(recetas[f[0]]),
            )
            for f in filas
        ]


class RepositorioProfesionalesPostgreSQL:
    def __init__(self, conexion: psycopg.Connection) -> None:
        self.conexion = conexion

    def obtener(self, id_profesional: str) -> ProfesionalLocal | None:
        try:
            uuid = UUID(id_profesional)
        except ValueError:
            return None
        fila = self.conexion.execute(
            "SELECT id_profesional_central, nombres, apellidos, rol, estado "
            "FROM personal_medico WHERE id_profesional_central = %s",
            (uuid,),
        ).fetchone()
        if fila is None:
            return None
        return ProfesionalLocal(
            str(fila[0]), fila[1], fila[2], fila[3].lower(), fila[4] == "Activo"
        )

    def sincronizar(self, perfil: ProfesionalLocal) -> None:
        # Mismo criterio que scripts/sincronizar_profesionales.py: no pisa un 'Suspendido'
        # puesto por el hospital mientras la cuenta siga activa.
        self.conexion.execute(
            "INSERT INTO personal_medico (nombres, apellidos, rol, estado, id_profesional_central) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (id_profesional_central) DO UPDATE SET "
            "  nombres = EXCLUDED.nombres, apellidos = EXCLUDED.apellidos, rol = EXCLUDED.rol, "
            "  estado = CASE WHEN EXCLUDED.estado = 'Inactivo' THEN 'Inactivo' "
            "                WHEN personal_medico.estado = 'Inactivo' THEN 'Activo' "
            "                ELSE personal_medico.estado END",
            (
                perfil.nombres,
                perfil.apellidos,
                ROL_PERSONAL_MEDICO.get(perfil.rol, "Administrativo"),
                "Activo" if perfil.activo else "Inactivo",
                UUID(perfil.id_profesional),
            ),
        )


class RepositorioCitasPostgreSQL:
    """Citas del hospital. La base impide los choques (restriccion de exclusion).

    El modelo original guarda `fecha` y `hora` locales del hospital; aqui se convierten
    desde/hacia la zona horaria configurada y la API siempre responde en UTC.
    """

    _COLUMNAS = (
        "c.id_cita, c.id_paciente, p.nombres || ' ' || p.apellidos, "
        "COALESCE(pm.id_profesional_central::text, 'sin-cuenta-' || pm.id_personal), "
        "c.fecha, c.hora, c.duracion_minutos, COALESCE(c.motivo, ''), c.estado, "
        "COALESCE(c.creada_por::text, ''), c.motivo_cambio "
        "FROM cita c JOIN paciente p ON p.id_paciente = c.id_paciente "
        "JOIN personal_medico pm ON pm.id_personal = c.id_personal "
    )

    def __init__(self, conexion: psycopg.Connection, zona: ZoneInfo) -> None:
        self.conexion = conexion
        self.zona = zona

    def _local(self, valor: datetime) -> datetime:
        return valor.astimezone(self.zona).replace(tzinfo=None)

    def _a_cita(self, fila: tuple) -> Cita:
        inicio = datetime.combine(fila[4], fila[5], tzinfo=self.zona).astimezone(UTC)
        return Cita(
            id_cita=str(fila[0]),
            id_paciente=str(fila[1]),
            nombre_paciente=fila[2],
            id_profesional=fila[3],
            inicio=inicio,
            fin=inicio + timedelta(minutes=fila[6]),
            motivo=fila[7],
            estado=ESTADO_CITA_DOMINIO[fila[8]],
            creada_por=fila[9],
            motivo_cambio=fila[10],
        )

    def obtener(self, id_cita: str) -> Cita | None:
        numero = entero_positivo(id_cita)
        if numero is None:
            return None
        fila = self.conexion.execute(
            "SELECT " + self._COLUMNAS + "WHERE c.id_cita = %s", (numero,)
        ).fetchone()
        return self._a_cita(fila) if fila else None

    def agendar(self, datos: NuevaCita, nombre_paciente: str, creada_por: str) -> Cita:
        paciente = entero_positivo(datos.id_paciente)
        if paciente is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        try:
            profesional, quien = UUID(datos.id_profesional), UUID(creada_por)
        except ValueError as error:
            raise ProfesionalNoVinculado("La cuenta o el profesional no son validos.") from error
        fila = self.conexion.execute(
            "SELECT id_personal FROM personal_medico WHERE id_profesional_central = %s",
            (profesional,),
        ).fetchone()
        if fila is None:
            raise DatosInvalidos("El profesional no existe, no esta activo o no atiende.")
        local = self._local(datos.inicio)
        try:
            id_cita = self.conexion.execute(
                "INSERT INTO cita (id_paciente, id_personal, fecha, hora, duracion_minutos, "
                "motivo, estado, creada_por) VALUES (%s, %s, %s, %s, %s, %s, 'Programada', %s) "
                "RETURNING id_cita",
                (
                    paciente,
                    fila[0],
                    local.date(),
                    local.time(),
                    datos.duracion_minutos,
                    datos.motivo,
                    quien,
                ),
            ).fetchone()[0]
        except psycopg.errors.ExclusionViolation as error:
            raise ConflictoAgenda("El profesional ya tiene una cita en ese horario.") from error
        except psycopg.errors.CheckViolation as error:
            if "archivado" in str(error):
                raise PacienteArchivado(
                    "El historial esta archivado; no admite citas nuevas."
                ) from error
            raise DatosInvalidos(
                "El profesional no existe, no esta activo o no atiende."
            ) from error
        cita = self.obtener(str(id_cita))
        assert cita is not None
        return cita

    def listar_agenda(
        self, desde: datetime, hasta: datetime, id_profesional: str | None = None
    ) -> list[Cita]:
        filtro, parametros = "", [self._local(desde), self._local(hasta)]
        if id_profesional is not None:
            try:
                parametros.append(UUID(id_profesional))
            except ValueError:
                return []
            filtro = "AND pm.id_profesional_central = %s "
        filas = self.conexion.execute(
            "SELECT "
            + self._COLUMNAS
            + "WHERE c.fecha + c.hora >= %s AND c.fecha + c.hora < %s "
            + filtro
            + "ORDER BY c.fecha + c.hora, c.id_cita LIMIT 500",
            parametros,
        ).fetchall()
        return [self._a_cita(f) for f in filas]

    def listar_por_paciente(self, id_paciente: str, limite: int) -> list[Cita]:
        numero = entero_positivo(id_paciente)
        if numero is None:
            return []
        filas = self.conexion.execute(
            "SELECT " + self._COLUMNAS + "WHERE c.id_paciente = %s "
            "ORDER BY c.fecha DESC, c.hora DESC, c.id_cita DESC LIMIT %s",
            (numero, limite),
        ).fetchall()
        return [self._a_cita(f) for f in filas]

    def cambiar_estado(
        self, id_cita: str, estado: EstadoCita, por: str, motivo: str | None
    ) -> Cita:
        numero = entero_positivo(id_cita)
        if numero is None:
            raise CitaNoEncontrada("La cita no existe en tu institucion.")
        try:
            quien = UUID(por)
        except ValueError as error:
            raise ProfesionalNoVinculado("La cuenta no es valida.") from error
        # FOR UPDATE: dos cambios simultaneos sobre la misma cita se aplican uno tras otro.
        fila = self.conexion.execute(
            "SELECT estado FROM cita WHERE id_cita = %s FOR UPDATE", (numero,)
        ).fetchone()
        if fila is None:
            raise CitaNoEncontrada("La cita no existe en tu institucion.")
        actual = ESTADO_CITA_DOMINIO[fila[0]]
        if estado not in TRANSICIONES.get(actual, set()):
            raise ConflictoAgenda(f"Una cita '{actual}' no puede pasar a '{estado}'.")
        self.conexion.execute(
            "UPDATE cita SET estado = %s, motivo_cambio = %s, actualizada_por = %s "
            "WHERE id_cita = %s",
            (ESTADO_CITA_BD[estado], motivo, quien, numero),
        )
        cita = self.obtener(id_cita)
        assert cita is not None
        return cita


class UnidadTrabajoPostgreSQL:
    """Cada solicitud abre su conexion y la cierra; sin commit() todo se revierte."""

    def __init__(
        self,
        dsn: str,
        conectar: Callable[[], psycopg.Connection] | None = None,
        zona: ZoneInfo | None = None,
    ) -> None:
        self.dsn = dsn
        self.zona = zona or ZoneInfo("America/Guatemala")
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
        self.profesionales = RepositorioProfesionalesPostgreSQL(self.conexion)
        self.citas = RepositorioCitasPostgreSQL(self.conexion, self.zona)
        self.cobros = RepositorioCobrosPostgreSQL(self.conexion)
        self.hospital = RepositorioHospitalPostgreSQL(
            self.conexion, self.zona, self.historial._id_personal
        )
        # El odontograma es propio de la clinica odontologica (HTTP 501 aqui).
        pendientes = repositorios_pendientes(MOTOR)
        self.odontograma = pendientes["odontograma"]
        self.crecimiento = pendientes["crecimiento"]
        self.vacunacion = pendientes["vacunacion"]
        self.laboratorio = pendientes["laboratorio"]
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
