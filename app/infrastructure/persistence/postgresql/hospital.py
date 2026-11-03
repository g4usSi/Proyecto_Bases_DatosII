"""Hospital General (PostgreSQL): departamentos, camas, ingresos, altas y ordenes medicas.

Usa el esquema original (departamento, habitacion, cama, atencion de tipo INGRESO, ingreso,
diagnostico, orden_medica, receta) con las reglas de 010 y 013. Las fechas se guardan en
UTC sin zona, igual que las consultas.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg

from app.domain.cita import EstadoCita
from app.domain.consulta import Diagnostico, Receta
from app.domain.errores import (
    ConflictoEstado,
    PacienteArchivado,
    PacienteNoEncontrado,
    RegistroNoEncontrado,
)
from app.domain.hospital import (
    Cama,
    Departamento,
    EstadoCama,
    Ingreso,
    NuevaOrdenMedica,
    NuevoIngreso,
    OcupanteCama,
    OrdenMedica,
    PerfilHospital,
    ResumenAtencion,
    ResumenHospital,
    TipoAtencion,
    TipoIngreso,
    TipoOrdenMedica,
)
from app.infrastructure.persistence.comun import con_utc, entero_positivo, utc_ingenuo

ESTADO_CAMA_BD = {
    EstadoCama.DISPONIBLE: "Disponible",
    EstadoCama.OCUPADA: "Ocupada",
    EstadoCama.LIMPIEZA: "Limpieza",
    EstadoCama.MANTENIMIENTO: "Mantenimiento",
}
ESTADO_CAMA_DOMINIO = {v: k for k, v in ESTADO_CAMA_BD.items()}
TIPO_INGRESO_BD = {
    TipoIngreso.EMERGENCIA: "Emergencia",
    TipoIngreso.PROGRAMADO: "Programado",
    TipoIngreso.TRASLADO: "Traslado",
}
TIPO_INGRESO_DOMINIO = {v: k for k, v in TIPO_INGRESO_BD.items()}
TIPO_ORDEN_BD = {
    TipoOrdenMedica.MEDICAMENTO: "Medicamento",
    TipoOrdenMedica.EXAMEN: "Examen",
    TipoOrdenMedica.PROCEDIMIENTO: "Procedimiento",
    TipoOrdenMedica.INTERCONSULTA: "Interconsulta",
}
TIPO_ORDEN_DOMINIO = {v: k for k, v in TIPO_ORDEN_BD.items()}
ESTADO_CITA_DOMINIO = {
    "Programada": EstadoCita.PROGRAMADA,
    "Confirmada": EstadoCita.CONFIRMADA,
    "Atendida": EstadoCita.ATENDIDA,
    "Cancelada": EstadoCita.CANCELADA,
    "No_asistio": EstadoCita.NO_ASISTIO,
}
_PROFESIONAL = "COALESCE(pm.id_profesional_central::text, 'sin-cuenta-' || pm.id_personal)"

_CAMAS = """
SELECT c.id_cama, c.codigo, h.id_habitacion, h.numero, d.id_departamento, d.descripcion,
       c.estado_operativo, i.id_atencion, a.id_paciente, p.nombres || ' ' || p.apellidos,
       i.tipo, i.fecha_hora_ingreso
FROM cama c
JOIN habitacion h ON h.id_habitacion = c.id_habitacion
JOIN departamento d ON d.id_departamento = h.id_departamento
LEFT JOIN ingreso i ON i.id_cama = c.id_cama AND i.fecha_hora_alta IS NULL
LEFT JOIN atencion a ON a.id_atencion = i.id_atencion
LEFT JOIN paciente p ON p.id_paciente = a.id_paciente
"""

_INGRESOS = f"""
SELECT a.id_atencion, a.id_paciente, p.nombres || ' ' || p.apellidos, {_PROFESIONAL},
       i.tipo, COALESCE(a.motivo, a.detalle, ''), i.id_cama, c.codigo, d.descripcion,
       i.fecha_hora_ingreso, i.fecha_hora_alta, i.motivo_alta
FROM ingreso i
JOIN atencion a ON a.id_atencion = i.id_atencion AND a.tipo_atencion = 'INGRESO'
JOIN paciente p ON p.id_paciente = a.id_paciente
JOIN personal_medico pm ON pm.id_personal = a.id_personal
JOIN cama c ON c.id_cama = i.id_cama
JOIN habitacion h ON h.id_habitacion = c.id_habitacion
JOIN departamento d ON d.id_departamento = h.id_departamento
"""


def _cama(fila: tuple) -> Cama:
    ocupante = None
    if fila[7] is not None:
        ocupante = OcupanteCama(
            str(fila[7]), str(fila[8]), fila[9], TIPO_INGRESO_DOMINIO[fila[10]], con_utc(fila[11])
        )
    return Cama(
        id_cama=fila[0],
        codigo=fila[1],
        id_habitacion=fila[2],
        habitacion=fila[3],
        id_departamento=fila[4],
        departamento=fila[5],
        estado=ESTADO_CAMA_DOMINIO[fila[6]],
        ocupante=ocupante,
    )


class RepositorioHospitalPostgreSQL:
    def __init__(
        self,
        conexion: psycopg.Connection,
        zona: ZoneInfo,
        id_personal: Any,
    ) -> None:
        self.conexion = conexion
        self.zona = zona
        # Resuelve la cuenta central -> personal_medico activo (ProfesionalNoVinculado si no).
        self._id_personal = id_personal

    # ------------------------------------------------------------------ infraestructura

    def listar_atenciones(
        self, id_paciente=None, tipo=None, desde=None, hasta=None, limite=50, antes_de=None
    ):
        filtros, valores = [], []
        for condicion, valor in (
            (
                "a.id_paciente = %s",
                entero_positivo(id_paciente) if id_paciente is not None else None,
            ),
            ("a.tipo_atencion = %s", tipo.value if tipo else None),
            ("a.fecha_hora >= %s", utc_ingenuo(desde) if desde else None),
            ("a.fecha_hora < %s", utc_ingenuo(hasta) if hasta else None),
            ("a.id_atencion < %s", antes_de),
        ):
            if valor is not None:
                filtros.append(condicion)
                valores.append(valor)
        if id_paciente is not None and entero_positivo(id_paciente) is None:
            return []
        donde = " WHERE " + " AND ".join(filtros) if filtros else ""
        filas = self.conexion.execute(
            "SELECT a.id_atencion, a.tipo_atencion, a.id_paciente, "
            "p.nombres || ' ' || p.apellidos, "
            f"{_PROFESIONAL}, pm.nombres || ' ' || pm.apellidos, a.fecha_hora, "
            "COALESCE(a.motivo, a.detalle, ''), a.id_cita, c.codigo, i.tipo, i.fecha_hora_alta, "
            "cb.id_cobro, cb.estado FROM atencion a "
            "JOIN paciente p ON p.id_paciente = a.id_paciente "
            "JOIN personal_medico pm ON pm.id_personal = a.id_personal "
            "LEFT JOIN ingreso i ON i.id_atencion = a.id_atencion "
            "LEFT JOIN cama c ON c.id_cama = i.id_cama "
            "LEFT JOIN LATERAL (SELECT id_cobro, estado FROM cobro "
            "WHERE id_atencion = a.id_atencion ORDER BY (estado <> 'Anulado') DESC, "
            "id_cobro DESC LIMIT 1) cb ON TRUE " + donde + " ORDER BY a.id_atencion DESC LIMIT %s",
            (*valores, limite),
        ).fetchall()
        return [
            ResumenAtencion(
                str(f[0]),
                TipoAtencion(f[1]),
                str(f[2]),
                f[3],
                f[4],
                f[5],
                con_utc(f[6]),
                f[7],
                str(f[8]) if f[8] else None,
                f[9],
                TIPO_INGRESO_DOMINIO[f[10]] if f[10] else None,
                con_utc(f[11]) if f[11] else None,
                str(f[12]) if f[12] else None,
                f[13].lower() if f[13] else None,
            )
            for f in filas
        ]

    def obtener_atencion(self, id_paciente, id_atencion):
        numero = entero_positivo(id_atencion)
        if numero is None:
            return None
        filas = self.listar_atenciones(id_paciente=id_paciente, antes_de=numero + 1, limite=1)
        return filas[0] if filas and int(filas[0].id_atencion) == numero else None

    def perfil(self, id_profesional):
        from uuid import UUID

        try:
            identificador = UUID(id_profesional)
        except ValueError:
            return None
        fila = self.conexion.execute(
            "SELECT pm.colegiado, pm.telefono, pm.estado, "
            "COALESCE(array_agg(e.nombre ORDER BY e.nombre) "
            "FILTER (WHERE e.nombre IS NOT NULL), '{}') "
            "FROM personal_medico pm "
            "LEFT JOIN personal_especialidad pe ON pe.id_personal = pm.id_personal "
            "LEFT JOIN especialidad e ON e.id_especialidad = pe.id_especialidad "
            "WHERE pm.id_profesional_central = %s GROUP BY pm.id_personal",
            (identificador,),
        ).fetchone()
        return PerfilHospital(fila[0], tuple(fila[3]), fila[1], fila[2]) if fila else None

    def cambiar_grupo_sanguineo(self, id_paciente, grupo):
        if grupo is not None and grupo not in {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}:
            from app.domain.errores import DatosInvalidos

            raise DatosInvalidos("Grupo sanguineo invalido.")
        fila = self.conexion.execute(
            "SELECT estado FROM paciente WHERE id_paciente = %s FOR UPDATE",
            (entero_positivo(id_paciente),),
        ).fetchone()
        if fila is None:
            raise PacienteNoEncontrado("El paciente no existe.")
        if fila[0] == "Inactivo":
            raise PacienteArchivado("El historial esta archivado.")
        self.conexion.execute(
            "UPDATE paciente SET grupo_sanguineo = %s WHERE id_paciente = %s",
            (grupo, entero_positivo(id_paciente)),
        )

    def listar_departamentos(self) -> list[Departamento]:
        return [
            Departamento(*fila)
            for fila in self.conexion.execute(
                "SELECT d.id_departamento, d.descripcion, "
                "  (SELECT count(*) FROM habitacion x WHERE x.id_departamento = d.id_departamento),"
                "  count(c.id_cama), "
                "  count(c.id_cama) FILTER (WHERE c.estado_operativo = 'Disponible') "
                "FROM departamento d "
                "LEFT JOIN habitacion h ON h.id_departamento = d.id_departamento "
                "LEFT JOIN cama c ON c.id_habitacion = h.id_habitacion "
                "GROUP BY d.id_departamento ORDER BY d.descripcion, d.id_departamento"
            )
        ]

    def listar_camas(
        self, id_departamento: int | None = None, estado: EstadoCama | None = None
    ) -> list[Cama]:
        filtros, parametros = [], []
        if id_departamento is not None:
            filtros.append("d.id_departamento = %s")
            parametros.append(id_departamento)
        if estado is not None:
            filtros.append("c.estado_operativo = %s")
            parametros.append(ESTADO_CAMA_BD[estado])
        donde = (" WHERE " + " AND ".join(filtros)) if filtros else ""
        filas = self.conexion.execute(
            _CAMAS + donde + " ORDER BY d.descripcion, h.numero, c.codigo, c.id_cama", parametros
        ).fetchall()
        return [_cama(f) for f in filas]

    def obtener_cama(self, id_cama: int) -> Cama | None:
        fila = self.conexion.execute(_CAMAS + " WHERE c.id_cama = %s", (id_cama,)).fetchone()
        return _cama(fila) if fila else None

    def cambiar_estado_cama(self, id_cama: int, estado: EstadoCama) -> Cama:
        try:
            cambiadas = self.conexion.execute(
                "UPDATE cama SET estado_operativo = %s WHERE id_cama = %s",
                (ESTADO_CAMA_BD[estado], id_cama),
            ).rowcount
        except psycopg.errors.CheckViolation as error:
            raise ConflictoEstado(
                "La cama tiene un paciente ingresado: da el alta primero."
            ) from error
        if not cambiadas:
            raise RegistroNoEncontrado("La cama no existe.")
        cama = self.obtener_cama(id_cama)
        assert cama is not None
        return cama

    # ------------------------------------------------------------------ ingresos

    def _paciente_activo(self, numero: int) -> None:
        """Bloquea la fila: una baja concurrente espera a que termine este ingreso."""
        fila = self.conexion.execute(
            "SELECT estado FROM paciente WHERE id_paciente = %s FOR SHARE", (numero,)
        ).fetchone()
        if fila is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        if fila[0] == "Inactivo":
            raise PacienteArchivado("El historial esta archivado; no admite ingresos.")

    def ingresar(
        self, id_paciente: str, id_profesional: str, datos: NuevoIngreso, ahora: datetime
    ) -> Ingreso:
        numero = entero_positivo(id_paciente)
        if numero is None:
            raise PacienteNoEncontrado("El paciente no existe en tu institucion.")
        id_personal = self._id_personal(id_profesional)
        self._paciente_activo(numero)
        if self.obtener_cama(datos.id_cama) is None:
            raise RegistroNoEncontrado("La cama no existe.")
        momento = utc_ingenuo(ahora)
        try:
            id_atencion = self.conexion.execute(
                "INSERT INTO atencion (id_paciente, id_personal, tipo_atencion, fecha_hora, "
                "motivo) "
                "VALUES (%s, %s, 'INGRESO', %s, %s) RETURNING id_atencion",
                (numero, id_personal, momento, datos.motivo),
            ).fetchone()[0]
            self.conexion.execute(
                "INSERT INTO ingreso (id_atencion, id_cama, fecha_hora_ingreso, tipo) "
                "VALUES (%s, %s, %s, %s)",
                (id_atencion, datos.id_cama, momento, TIPO_INGRESO_BD[datos.tipo]),
            )
        except psycopg.errors.ExclusionViolation as error:
            raise ConflictoEstado("La cama ya esta ocupada en ese periodo.") from error
        except psycopg.errors.CheckViolation as error:
            mensaje = str(error.diag.message_primary or "")
            if "archivado" in mensaje:
                raise PacienteArchivado("El historial esta archivado.") from error
            if "paciente ya tiene un ingreso" in mensaje:
                raise ConflictoEstado("El paciente ya esta ingresado en otra cama.") from error
            raise ConflictoEstado("La cama no esta disponible.") from error
        for d in datos.diagnosticos:
            self._insertar_diagnostico(id_atencion, d)
        ingreso = self.obtener_ingreso(id_paciente, str(id_atencion))
        assert ingreso is not None
        return ingreso

    def _insertar_diagnostico(self, id_atencion: int, d: Diagnostico) -> None:
        self.conexion.execute(
            "INSERT INTO diagnostico (id_atencion, descripcion, codigo, sistema_codigo) "
            "VALUES (%s, %s, %s, %s)",
            (id_atencion, d.descripcion, d.codigo, d.sistema_codigo),
        )

    def _cargar(self, filas: list[tuple]) -> list[Ingreso]:
        if not filas:
            return []
        ids = [f[0] for f in filas]
        diagnosticos: dict[int, list[Diagnostico]] = {i: [] for i in ids}
        for id_atencion, descripcion, codigo, sistema in self.conexion.execute(
            "SELECT id_atencion, descripcion, codigo, sistema_codigo FROM diagnostico "
            "WHERE id_atencion = ANY(%s) ORDER BY id_diagnostico",
            (ids,),
        ):
            diagnosticos[id_atencion].append(Diagnostico(descripcion, codigo, sistema))
        recetas: dict[int, list[Receta]] = {}
        for fila in self.conexion.execute(
            "SELECT r.id_orden, dr.medicamento, dr.dosis, dr.frecuencia, dr.via_administracion, "
            "dr.duracion_dias, dr.indicaciones FROM detalle_receta dr "
            "JOIN receta r ON r.id_receta = dr.id_receta "
            "JOIN orden_medica o ON o.id_orden = r.id_orden "
            "WHERE o.id_atencion = ANY(%s) ORDER BY dr.id_detalle",
            (ids,),
        ):
            recetas.setdefault(fila[0], []).append(
                Receta(fila[1], fila[2] or "", fila[3] or "", fila[4], fila[5], fila[6])
            )
        ordenes: dict[int, list[OrdenMedica]] = {i: [] for i in ids}
        for id_orden, id_atencion, tipo, fecha, descripcion, profesional in self.conexion.execute(
            f"SELECT o.id_orden, o.id_atencion, o.tipo_orden, o.fecha_hora, o.descripcion, "
            f"{_PROFESIONAL} FROM orden_medica o "
            "JOIN personal_medico pm ON pm.id_personal = o.id_personal "
            "WHERE o.id_atencion = ANY(%s) ORDER BY o.fecha_hora, o.id_orden",
            (ids,),
        ):
            ordenes[id_atencion].append(
                OrdenMedica(
                    str(id_orden),
                    TIPO_ORDEN_DOMINIO[tipo],
                    con_utc(fecha),
                    profesional,
                    descripcion,
                    tuple(recetas.get(id_orden, ())),
                )
            )
        return [
            Ingreso(
                id_ingreso=str(f[0]),
                id_paciente=str(f[1]),
                nombre_paciente=f[2],
                id_profesional=f[3],
                tipo=TIPO_INGRESO_DOMINIO[f[4]],
                motivo=f[5],
                id_cama=f[6],
                cama=f[7],
                departamento=f[8],
                ingreso_en=con_utc(f[9]),
                alta_en=con_utc(f[10]) if f[10] else None,
                motivo_alta=f[11],
                diagnosticos=tuple(diagnosticos[f[0]]),
                ordenes=tuple(ordenes[f[0]]),
            )
            for f in filas
        ]

    def obtener_ingreso(self, id_paciente: str, id_ingreso: str) -> Ingreso | None:
        paciente, ingreso = entero_positivo(id_paciente), entero_positivo(id_ingreso)
        if paciente is None or ingreso is None:
            return None
        filas = self.conexion.execute(
            _INGRESOS + " WHERE a.id_atencion = %s AND a.id_paciente = %s", (ingreso, paciente)
        ).fetchall()
        cargados = self._cargar(filas)
        return cargados[0] if cargados else None

    def listar_ingresos(
        self,
        id_paciente: str | None = None,
        abiertos: bool | None = None,
        tipo: TipoIngreso | None = None,
        limite: int = 100,
    ) -> list[Ingreso]:
        filtros, parametros = [], []
        if id_paciente is not None:
            numero = entero_positivo(id_paciente)
            if numero is None:
                return []
            filtros.append("a.id_paciente = %s")
            parametros.append(numero)
        if abiertos is not None:
            filtros.append(
                "i.fecha_hora_alta IS NULL" if abiertos else "i.fecha_hora_alta IS NOT NULL"
            )
        if tipo is not None:
            filtros.append("i.tipo = %s")
            parametros.append(TIPO_INGRESO_BD[tipo])
        donde = (" WHERE " + " AND ".join(filtros)) if filtros else ""
        filas = self.conexion.execute(
            _INGRESOS + donde + " ORDER BY i.fecha_hora_ingreso DESC, a.id_atencion DESC LIMIT %s",
            (*parametros, limite),
        ).fetchall()
        return self._cargar(filas)

    def _abierto(self, id_paciente: str, id_ingreso: str) -> int:
        """Bloquea el ingreso abierto: un alta simultanea espera (o este cambio ve el alta)."""
        paciente, ingreso = entero_positivo(id_paciente), entero_positivo(id_ingreso)
        fila = None
        if paciente is not None and ingreso is not None:
            fila = self.conexion.execute(
                "SELECT i.fecha_hora_alta FROM ingreso i "
                "JOIN atencion a ON a.id_atencion = i.id_atencion "
                "WHERE i.id_atencion = %s AND a.id_paciente = %s FOR UPDATE OF i",
                (ingreso, paciente),
            ).fetchone()
        if fila is None:
            raise RegistroNoEncontrado("El ingreso no existe en el historial del paciente.")
        if fila[0] is not None:
            raise ConflictoEstado("El ingreso ya tiene alta y no admite cambios.")
        return ingreso

    def agregar_diagnostico(
        self, id_paciente: str, id_ingreso: str, diagnostico: Diagnostico
    ) -> Ingreso:
        id_atencion = self._abierto(id_paciente, id_ingreso)
        try:
            self._insertar_diagnostico(id_atencion, diagnostico)
        except psycopg.errors.CheckViolation as error:
            raise PacienteArchivado("El historial esta archivado.") from error
        ingreso = self.obtener_ingreso(id_paciente, id_ingreso)
        assert ingreso is not None
        return ingreso

    def agregar_orden(
        self,
        id_paciente: str,
        id_ingreso: str,
        id_profesional: str,
        orden: NuevaOrdenMedica,
        ahora: datetime,
    ) -> Ingreso:
        id_personal = self._id_personal(id_profesional)
        id_atencion = self._abierto(id_paciente, id_ingreso)
        momento = utc_ingenuo(ahora)
        try:
            id_orden = self.conexion.execute(
                "INSERT INTO orden_medica (id_atencion, id_personal, fecha_hora, tipo_orden, "
                "descripcion) VALUES (%s, %s, %s, %s, %s) RETURNING id_orden",
                (id_atencion, id_personal, momento, TIPO_ORDEN_BD[orden.tipo], orden.descripcion),
            ).fetchone()[0]
        except psycopg.errors.CheckViolation as error:
            raise PacienteArchivado("El historial esta archivado.") from error
        if orden.recetas:
            id_receta = self.conexion.execute(
                "INSERT INTO receta (id_orden, fecha_hora) VALUES (%s, %s) RETURNING id_receta",
                (id_orden, momento),
            ).fetchone()[0]
            for r in orden.recetas:
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
        ingreso = self.obtener_ingreso(id_paciente, id_ingreso)
        assert ingreso is not None
        return ingreso

    def dar_alta(self, id_paciente: str, id_ingreso: str, motivo: str, ahora: datetime) -> Ingreso:
        id_atencion = self._abierto(id_paciente, id_ingreso)
        # Condicional: si otra solicitud dio el alta primero, no se sobrescribe.
        cambiados = self.conexion.execute(
            "UPDATE ingreso SET fecha_hora_alta = %s, motivo_alta = %s "
            "WHERE id_atencion = %s AND fecha_hora_alta IS NULL",
            (utc_ingenuo(ahora), motivo, id_atencion),
        ).rowcount
        if not cambiados:
            raise ConflictoEstado("El ingreso ya tiene alta.")
        ingreso = self.obtener_ingreso(id_paciente, id_ingreso)
        assert ingreso is not None
        return ingreso

    # ------------------------------------------------------------------ resumen

    def resumen(self, hoy: date) -> ResumenHospital:
        inicio = utc_ingenuo(datetime.combine(hoy, time.min, tzinfo=self.zona).astimezone(UTC))
        fin = inicio + timedelta(days=1)
        camas = {estado.value: 0 for estado in EstadoCama}
        for estado, total in self.conexion.execute(
            "SELECT estado_operativo, count(*) FROM cama GROUP BY estado_operativo"
        ):
            camas[ESTADO_CAMA_DOMINIO[estado].value] = total
        abiertos, emergencias, ingresos_hoy, altas_hoy = self.conexion.execute(
            "SELECT count(*) FILTER (WHERE fecha_hora_alta IS NULL), "
            "count(*) FILTER (WHERE fecha_hora_alta IS NULL AND tipo = 'Emergencia'), "
            "count(*) FILTER (WHERE fecha_hora_ingreso >= %s AND fecha_hora_ingreso < %s), "
            "count(*) FILTER (WHERE fecha_hora_alta >= %s AND fecha_hora_alta < %s) "
            "FROM ingreso",
            (inicio, fin, inicio, fin),
        ).fetchone()
        citas = {estado.value: 0 for estado in EstadoCita}
        for estado, total in self.conexion.execute(
            "SELECT estado, count(*) FROM cita WHERE fecha = %s GROUP BY estado", (hoy,)
        ):
            citas[ESTADO_CITA_DOMINIO[estado].value] = total
        return ResumenHospital(camas, abiertos, emergencias, ingresos_hoy, altas_hoy, citas)
