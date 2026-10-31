"""Administracion de cuentas en la identidad central (PostgreSQL, esquema identidad).

Cada operacion abre su conexion y hace UNA transaccion: el cambio de la cuenta y su
evento en identidad.bitacora_profesionales se guardan juntos o no se guarda nada.

Todo se filtra por un Alcance: el administrador ve su entidad sin cuentas de
administracion; el superusuario, todas (o la pedida) con sus administradores. El
superusuario nunca aparece y las cuentas eliminadas no salen en los listados.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.application.errores import IntegracionNoConfigurada
from app.domain.administracion import (
    ROL_ADMINISTRADOR,
    ROL_SUPERUSUARIO,
    ROLES_POR_INSTITUCION,
    AccionBitacora,
    Alcance,
    CambiosProfesional,
    CuentaAtencion,
    EntradaBitacora,
    EstadoCuenta,
    FichaProfesional,
    FiltroBitacora,
    NuevoProfesional,
    ProfesionalAgenda,
    ResumenPersonal,
)
from app.domain.errores import ConflictoEstado, DatosInvalidos, RegistroNoEncontrado
from app.domain.institucion import Institucion

# Bloqueo puesto por la administracion (indefinido). El bloqueo por intentos fallidos
# usa una fecha cercana; restablecer la contrasena solo quita ese ultimo.
BLOQUEO_ADMINISTRATIVO = datetime(9999, 12, 31, tzinfo=UTC)

_ESTADO_SQL = (
    "CASE WHEN p.eliminado_en IS NOT NULL THEN 'eliminada' "
    "WHEN NOT p.activo THEN 'inactiva' "
    "WHEN p.bloqueado_hasta IS NOT NULL AND p.bloqueado_hasta > now() THEN 'bloqueada' "
    "ELSE 'activa' END"
)

_FICHA = f"""
SELECT p.id_profesional, p.correo, p.nombres, p.apellidos, p.rol, p.establecimiento,
       {_ESTADO_SQL} AS estado, p.id_departamento, d.descripcion AS departamento,
       p.debe_cambiar_contrasena, p.creado_en, p.actualizado_en,
       COALESCE(array_agg(pp.permiso ORDER BY pp.permiso)
                FILTER (WHERE pp.permiso IS NOT NULL), '{{}}') AS permisos
FROM identidad.profesional p
LEFT JOIN public.departamento d ON d.id_departamento = p.id_departamento
LEFT JOIN identidad.profesional_permiso pp ON pp.id_profesional = p.id_profesional
WHERE {{alcance}} {{filtro}}
GROUP BY p.id_profesional, d.descripcion
"""

_INDICE_ADMIN_UNICO = "ux_un_admin_por_entidad"


def _alcance_sql(alcance: Alcance, parametros: dict[str, Any]) -> str:
    """Condiciones del alcance sobre identidad.profesional (alias p)."""
    condiciones = [f"p.rol <> '{ROL_SUPERUSUARIO}'"]
    if alcance.institucion is not None:
        condiciones.append("p.establecimiento = %(institucion)s")
        parametros["institucion"] = alcance.institucion.value
    if not alcance.incluir_administradores:
        condiciones.append(f"p.rol <> '{ROL_ADMINISTRADOR}'")
    return " AND ".join(condiciones)


def _conflicto_unico(error: psycopg.errors.UniqueViolation) -> ConflictoEstado:
    if error.diag.constraint_name == _INDICE_ADMIN_UNICO:
        return ConflictoEstado("Esa entidad ya tiene un administrador activo.")
    return ConflictoEstado("Ya existe una cuenta con ese correo.")


def _uuid(texto: str) -> UUID | None:
    try:
        return UUID(texto)
    except ValueError:
        return None


def _ficha(fila: dict[str, Any]) -> FichaProfesional:
    return FichaProfesional(
        id_profesional=str(fila["id_profesional"]),
        correo=fila["correo"],
        nombres=fila["nombres"],
        apellidos=fila["apellidos"],
        rol=fila["rol"],
        institucion=Institucion(fila["establecimiento"]) if fila["establecimiento"] else None,
        estado=EstadoCuenta(fila["estado"]),
        permisos=frozenset(fila["permisos"]),
        id_departamento=fila["id_departamento"],
        departamento=fila["departamento"],
        debe_cambiar_contrasena=fila["debe_cambiar_contrasena"],
        creado_en=fila["creado_en"],
        actualizado_en=fila["actualizado_en"],
    )


class AdministracionPostgreSQL:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _conectar(self) -> psycopg.Connection:
        try:
            return psycopg.connect(
                self._dsn,
                connect_timeout=5,
                row_factory=dict_row,
                options="-c statement_timeout=10000",
            )
        except psycopg.Error as error:
            raise IntegracionNoConfigurada(
                "El directorio de profesionales no esta disponible."
            ) from error

    def _leer(
        self, conexion: psycopg.Connection, alcance: Alcance, id_profesional: UUID
    ) -> FichaProfesional | None:
        parametros: dict[str, Any] = {"id": id_profesional}
        consulta = _FICHA.replace("{alcance}", _alcance_sql(alcance, parametros)).replace(
            "{filtro}", "AND p.id_profesional = %(id)s"
        )
        fila = conexion.execute(consulta, parametros).fetchone()
        return _ficha(fila) if fila else None

    def _bloquear(
        self, conexion: psycopg.Connection, alcance: Alcance, identificador: UUID
    ) -> dict[str, Any] | None:
        """Bloquea la fila de la cuenta (FOR UPDATE) si esta dentro del alcance."""
        parametros: dict[str, Any] = {"id": identificador}
        condicion = _alcance_sql(alcance, parametros)
        return conexion.execute(
            "SELECT p.rol, p.activo, p.bloqueado_hasta, p.id_departamento, p.nombres, "
            "p.apellidos, p.establecimiento, p.eliminado_en "
            f"FROM identidad.profesional p WHERE p.id_profesional = %(id)s AND {condicion} "
            "FOR UPDATE",
            parametros,
        ).fetchone()

    @staticmethod
    def _bitacora(
        conexion: psycopg.Connection,
        id_actor: str,
        id_profesional: UUID,
        institucion: str | None,
        accion: str,
        detalle: dict[str, Any],
    ) -> None:
        conexion.execute(
            "INSERT INTO identidad.bitacora_profesionales "
            "(id_actor, id_profesional, establecimiento, accion, detalle) "
            "VALUES (%s, %s, %s, %s, %s)",
            (UUID(id_actor), id_profesional, institucion, accion, Jsonb(detalle)),
        )

    # ------------------------------------------------------------------ escritura

    def crear(
        self,
        institucion: Institucion,
        datos: NuevoProfesional,
        permisos: frozenset[str],
        contrasena_cifrada: str,
        id_actor: str,
    ) -> FichaProfesional:
        identificador = uuid4()
        try:
            with self._conectar() as conexion, conexion.transaction():
                conexion.execute(
                    "INSERT INTO identidad.profesional (id_profesional, correo, nombres, "
                    "apellidos, password_hash, establecimiento, rol, id_departamento, "
                    "debe_cambiar_contrasena) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)",
                    (
                        identificador,
                        datos.correo,
                        datos.nombres,
                        datos.apellidos,
                        contrasena_cifrada,
                        institucion.value,
                        datos.rol,
                        datos.id_departamento,
                    ),
                )
                for permiso in sorted(permisos):
                    conexion.execute(
                        "INSERT INTO identidad.profesional_permiso VALUES (%s, %s)",
                        (identificador, permiso),
                    )
                self._bitacora(
                    conexion,
                    id_actor,
                    identificador,
                    institucion.value,
                    "alta",
                    {
                        "rol": datos.rol,
                        "permisos": sorted(permisos),
                        "id_departamento": datos.id_departamento,
                    },
                )
                ficha = self._leer(conexion, Alcance(institucion, True), identificador)
        except psycopg.errors.UniqueViolation as error:
            raise _conflicto_unico(error) from error
        except psycopg.errors.ForeignKeyViolation as error:
            raise DatosInvalidos("El area (departamento) o un permiso no existe.") from error
        except psycopg.errors.CheckViolation as error:
            raise DatosInvalidos("La base rechazo el rol, el area o los permisos.") from error
        except psycopg.Error as error:
            raise IntegracionNoConfigurada("No se pudo crear la cuenta.") from error
        assert ficha is not None
        return ficha

    def actualizar(
        self,
        alcance: Alcance,
        id_profesional: str,
        cambios: CambiosProfesional,
        permisos: frozenset[str] | None,
        id_actor: str,
    ) -> FichaProfesional:
        identificador = _uuid(id_profesional)
        if identificador is None:
            raise RegistroNoEncontrado("El profesional no existe en tu institucion.")
        try:
            with self._conectar() as conexion, conexion.transaction():
                actual = self._bloquear(conexion, alcance, identificador)
                if actual is None:
                    raise RegistroNoEncontrado("El profesional no existe en tu institucion.")
                if actual["eliminado_en"] is not None:
                    raise ConflictoEstado("La cuenta fue eliminada: ya no se puede modificar.")
                antes = self._leer(conexion, alcance, identificador)
                detalle: dict[str, Any] = {}
                asignaciones: list[str] = []
                valores: list[Any] = []
                for campo in ("nombres", "apellidos"):
                    nuevo = getattr(cambios, campo)
                    if nuevo is not None and nuevo != actual[campo]:
                        asignaciones.append(f"{campo} = %s")
                        valores.append(nuevo)
                        detalle[campo] = "corregido"
                if cambios.quitar_departamento or cambios.id_departamento is not None:
                    nuevo_dep = None if cambios.quitar_departamento else cambios.id_departamento
                    if nuevo_dep != actual["id_departamento"]:
                        asignaciones.append("id_departamento = %s")
                        valores.append(nuevo_dep)
                        detalle["id_departamento"] = {
                            "antes": actual["id_departamento"],
                            "despues": nuevo_dep,
                        }
                if cambios.estado is not None and antes is not None:
                    if cambios.estado != antes.estado:
                        detalle["estado"] = {
                            "antes": antes.estado.value,
                            "despues": cambios.estado.value,
                        }
                        if cambios.estado == EstadoCuenta.ACTIVA:
                            asignaciones += [
                                "activo = TRUE",
                                "bloqueado_hasta = NULL",
                                "fallos_login = 0",
                            ]
                        elif cambios.estado == EstadoCuenta.BLOQUEADA:
                            asignaciones += [
                                "activo = TRUE",
                                "bloqueado_hasta = %s",
                                "version_token = version_token + 1",
                            ]
                            valores.append(BLOQUEO_ADMINISTRATIVO)
                        else:
                            asignaciones += ["activo = FALSE", "version_token = version_token + 1"]
                if asignaciones:
                    conexion.execute(
                        "UPDATE identidad.profesional SET "
                        + ", ".join([*asignaciones, "actualizado_en = now()"])
                        + " WHERE id_profesional = %s",
                        (*valores, identificador),
                    )
                if permisos is not None and antes is not None and permisos != antes.permisos:
                    retirados = sorted(antes.permisos - permisos)
                    agregados = sorted(permisos - antes.permisos)
                    if retirados:
                        conexion.execute(
                            "DELETE FROM identidad.profesional_permiso "
                            "WHERE id_profesional = %s AND permiso = ANY(%s)",
                            (identificador, retirados),
                        )
                    for permiso in agregados:
                        conexion.execute(
                            "INSERT INTO identidad.profesional_permiso VALUES (%s, %s)",
                            (identificador, permiso),
                        )
                    if not asignaciones:
                        conexion.execute(
                            "UPDATE identidad.profesional SET actualizado_en = now() "
                            "WHERE id_profesional = %s",
                            (identificador,),
                        )
                    detalle["permisos"] = {"agregados": agregados, "retirados": retirados}
                if detalle:
                    self._bitacora(
                        conexion,
                        id_actor,
                        identificador,
                        actual["establecimiento"],
                        "cambio",
                        detalle,
                    )
                ficha = self._leer(conexion, alcance, identificador)
        except (RegistroNoEncontrado, DatosInvalidos, ConflictoEstado):
            raise
        except psycopg.errors.UniqueViolation as error:
            raise _conflicto_unico(error) from error
        except psycopg.errors.ForeignKeyViolation as error:
            raise DatosInvalidos("El area (departamento) o un permiso no existe.") from error
        except psycopg.errors.CheckViolation as error:
            raise DatosInvalidos("La base rechazo el area o los permisos.") from error
        except psycopg.Error as error:
            raise IntegracionNoConfigurada("No se pudo actualizar la cuenta.") from error
        assert ficha is not None
        return ficha

    def eliminar(self, alcance: Alcance, id_profesional: str, id_actor: str) -> None:
        identificador = _uuid(id_profesional)
        if identificador is None:
            raise RegistroNoEncontrado("El profesional no existe.")
        try:
            with self._conectar() as conexion, conexion.transaction():
                actual = self._bloquear(conexion, alcance, identificador)
                if actual is None:
                    raise RegistroNoEncontrado("El profesional no existe.")
                if actual["eliminado_en"] is not None:
                    raise ConflictoEstado("La cuenta ya estaba eliminada.")
                antes = self._leer(conexion, alcance, identificador)
                conexion.execute(
                    "UPDATE identidad.profesional SET activo = FALSE, eliminado_en = now(), "
                    "version_token = version_token + 1, actualizado_en = now() "
                    "WHERE id_profesional = %s",
                    (identificador,),
                )
                self._bitacora(
                    conexion,
                    id_actor,
                    identificador,
                    actual["establecimiento"],
                    AccionBitacora.ELIMINAR.value,
                    {
                        "rol": actual["rol"],
                        "estado_anterior": antes.estado.value if antes else None,
                    },
                )
        except (RegistroNoEncontrado, ConflictoEstado):
            raise
        except psycopg.Error as error:
            raise IntegracionNoConfigurada("No se pudo eliminar la cuenta.") from error

    def establecer_contrasena(
        self,
        id_profesional: str,
        contrasena_cifrada: str,
        debe_cambiar: bool,
        id_actor: str,
        accion: str,
    ) -> None:
        identificador = _uuid(id_profesional)
        if identificador is None:
            raise RegistroNoEncontrado("El profesional no existe.")
        try:
            with self._conectar() as conexion, conexion.transaction():
                fila = conexion.execute(
                    "UPDATE identidad.profesional SET password_hash = %s, "
                    "debe_cambiar_contrasena = %s, version_token = version_token + 1, "
                    "fallos_login = 0, actualizado_en = now(), "
                    # Quita el bloqueo por intentos fallidos, no el puesto por administracion.
                    "bloqueado_hasta = CASE WHEN bloqueado_hasta >= %s "
                    "THEN bloqueado_hasta ELSE NULL END "
                    "WHERE id_profesional = %s RETURNING establecimiento",
                    (
                        contrasena_cifrada,
                        debe_cambiar,
                        BLOQUEO_ADMINISTRATIVO,
                        identificador,
                    ),
                ).fetchone()
                if fila is None:
                    raise RegistroNoEncontrado("El profesional no existe.")
                self._bitacora(
                    conexion, id_actor, identificador, fila["establecimiento"], accion, {}
                )
        except RegistroNoEncontrado:
            raise
        except psycopg.Error as error:
            raise IntegracionNoConfigurada("No se pudo cambiar la contrasena.") from error

    # ------------------------------------------------------------------ lectura

    def listar(
        self,
        alcance: Alcance,
        rol: str | None = None,
        id_departamento: int | None = None,
        estado: EstadoCuenta | None = None,
        limite: int = 200,
    ) -> list[FichaProfesional]:
        filtros = ["AND p.eliminado_en IS NULL"]
        parametros: dict[str, Any] = {"limite": limite}
        if rol is not None:
            filtros.append("AND p.rol = %(rol)s")
            parametros["rol"] = rol
        if id_departamento is not None:
            filtros.append("AND p.id_departamento = %(dep)s")
            parametros["dep"] = id_departamento
        if estado is not None:
            filtros.append(f"AND {_ESTADO_SQL} = %(estado)s")
            parametros["estado"] = estado.value
        consulta = (
            _FICHA.replace("{alcance}", _alcance_sql(alcance, parametros)).replace(
                "{filtro}", " ".join(filtros)
            )
            + f" ORDER BY p.establecimiento, (p.rol = '{ROL_ADMINISTRADOR}') DESC, "
            "p.apellidos, p.nombres, p.id_profesional LIMIT %(limite)s"
        )
        try:
            with self._conectar() as conexion:
                filas = conexion.execute(consulta, parametros).fetchall()
        except psycopg.Error as error:
            raise IntegracionNoConfigurada(
                "El directorio de profesionales no esta disponible."
            ) from error
        return [_ficha(f) for f in filas]

    def obtener(self, alcance: Alcance, id_profesional: str) -> FichaProfesional | None:
        identificador = _uuid(id_profesional)
        if identificador is None:
            return None
        try:
            with self._conectar() as conexion:
                return self._leer(conexion, alcance, identificador)
        except psycopg.Error as error:
            raise IntegracionNoConfigurada(
                "El directorio de profesionales no esta disponible."
            ) from error

    def listar_para_agenda(self, institucion: Institucion) -> list[ProfesionalAgenda]:
        try:
            with self._conectar() as conexion:
                filas = conexion.execute(
                    "SELECT id_profesional, nombres, apellidos, rol, id_departamento "
                    "FROM identidad.profesional WHERE establecimiento = %s AND activo "
                    "AND eliminado_en IS NULL "
                    "AND rol NOT IN ('secretaria', 'administrador') "
                    "ORDER BY apellidos, nombres, id_profesional",
                    (institucion.value,),
                ).fetchall()
        except psycopg.Error as error:
            raise IntegracionNoConfigurada(
                "El directorio de profesionales no esta disponible."
            ) from error
        return [
            ProfesionalAgenda(
                str(f["id_profesional"]),
                f["nombres"],
                f["apellidos"],
                f["rol"],
                f["id_departamento"],
            )
            for f in filas
        ]

    # ------------------------------------------------------------------ resumen y bitacora

    def resumen(self, institucion: Institucion) -> ResumenPersonal:
        personal = (
            "FROM identidad.profesional p WHERE p.establecimiento = %(inst)s "
            f"AND p.rol NOT IN ('{ROL_ADMINISTRADOR}', '{ROL_SUPERUSUARIO}') "
            "AND p.eliminado_en IS NULL"
        )
        parametros = {"inst": institucion.value, "indefinido": BLOQUEO_ADMINISTRATIVO}
        try:
            with self._conectar() as conexion:
                admin = conexion.execute(
                    "SELECT nombres || ' ' || apellidos AS nombre FROM identidad.profesional "
                    "WHERE establecimiento = %(inst)s AND rol = 'administrador' AND activo "
                    "AND eliminado_en IS NULL",
                    parametros,
                ).fetchone()
                por_estado = {e.value: 0 for e in EstadoCuenta if e != EstadoCuenta.ELIMINADA}
                for fila in conexion.execute(
                    f"SELECT {_ESTADO_SQL} AS estado, count(*) AS total {personal} GROUP BY 1",
                    parametros,
                ):
                    por_estado[fila["estado"]] = fila["total"]
                bloqueos = conexion.execute(
                    "SELECT count(*) FILTER (WHERE p.activo AND p.bloqueado_hasta > now() "
                    "AND p.bloqueado_hasta < %(indefinido)s) AS intentos, "
                    "count(*) FILTER (WHERE p.activo AND p.bloqueado_hasta >= %(indefinido)s) "
                    "AS administracion, "
                    f"count(*) FILTER (WHERE {_ESTADO_SQL} = 'activa' "
                    "AND p.debe_cambiar_contrasena) AS cambiar "
                    f"{personal}",
                    parametros,
                ).fetchone()
                por_rol = dict.fromkeys(sorted(ROLES_POR_INSTITUCION[institucion]), 0)
                for fila in conexion.execute(
                    f"SELECT p.rol, count(*) AS total {personal} AND {_ESTADO_SQL} = 'activa' "
                    "GROUP BY p.rol",
                    parametros,
                ):
                    por_rol[fila["rol"]] = fila["total"]
                por_area = None
                if institucion == Institucion.HOSPITAL_GENERAL:
                    por_area = tuple(
                        (f["id_departamento"], f["descripcion"], f["total"])
                        for f in conexion.execute(
                            "SELECT d.id_departamento, d.descripcion, count(p.id_profesional) "
                            "AS total FROM public.departamento d "
                            "LEFT JOIN identidad.profesional p "
                            "ON p.id_departamento = d.id_departamento "
                            f"AND p.rol NOT IN ('{ROL_ADMINISTRADOR}', '{ROL_SUPERUSUARIO}') "
                            f"AND {_ESTADO_SQL} = 'activa' "
                            "GROUP BY d.id_departamento, d.descripcion "
                            "ORDER BY d.descripcion, d.id_departamento"
                        )
                    )
                atencion = tuple(
                    CuentaAtencion(
                        str(f["id_profesional"]),
                        f["nombres"],
                        f["apellidos"],
                        f["rol"],
                        EstadoCuenta(f["estado"]),
                        f["motivo"],
                    )
                    for f in conexion.execute(
                        f"SELECT * FROM (SELECT p.id_profesional, p.nombres, p.apellidos, "
                        f"p.rol, {_ESTADO_SQL} AS estado, CASE "
                        "WHEN p.activo AND p.bloqueado_hasta > now() "
                        "AND p.bloqueado_hasta < %(indefinido)s THEN 'bloqueo_por_intentos' "
                        f"WHEN {_ESTADO_SQL} = 'activa' AND p.debe_cambiar_contrasena "
                        "THEN 'debe_cambiar_contrasena' END AS motivo "
                        f"{personal}) x WHERE motivo IS NOT NULL "
                        "ORDER BY motivo, apellidos, nombres LIMIT 50",
                        parametros,
                    )
                )
        except psycopg.Error as error:
            raise IntegracionNoConfigurada(
                "El directorio de profesionales no esta disponible."
            ) from error
        return ResumenPersonal(
            institucion=institucion,
            administrador=admin["nombre"] if admin else None,
            por_estado=por_estado,
            bloqueadas_por_intentos=bloqueos["intentos"],
            bloqueadas_por_administracion=bloqueos["administracion"],
            deben_cambiar_contrasena=bloqueos["cambiar"],
            activos_por_rol=por_rol,
            activos_por_area=por_area,
            requieren_atencion=atencion,
            ultimos_movimientos=tuple(
                self.bitacora(Alcance(institucion, True), FiltroBitacora(limite=5))
            ),
        )

    def bitacora(self, alcance: Alcance, filtro: FiltroBitacora) -> list[EntradaBitacora]:
        condiciones = ["TRUE"]
        parametros: dict[str, Any] = {"limite": filtro.limite}
        if alcance.institucion is not None:
            condiciones.append("b.establecimiento = %(inst)s")
            parametros["inst"] = alcance.institucion.value
        if filtro.acciones:
            condiciones.append("b.accion = ANY(%(acciones)s)")
            parametros["acciones"] = sorted(a.value for a in filtro.acciones)
        if filtro.desde is not None:
            condiciones.append("b.ocurrido_en >= %(desde)s")
            parametros["desde"] = filtro.desde
        if filtro.hasta is not None:
            condiciones.append("b.ocurrido_en < %(hasta)s")
            parametros["hasta"] = filtro.hasta
        if filtro.antes_de is not None:
            condiciones.append("b.id_evento < %(antes)s")
            parametros["antes"] = filtro.antes_de
        consulta = (
            "SELECT b.id_evento, b.ocurrido_en, b.accion, b.id_actor, "
            "a.nombres || ' ' || a.apellidos AS actor_nombre, a.rol AS actor_rol, "
            "b.id_profesional, o.nombres || ' ' || o.apellidos AS profesional_nombre, "
            "b.establecimiento, b.detalle "
            "FROM identidad.bitacora_profesionales b "
            "LEFT JOIN identidad.profesional a ON a.id_profesional = b.id_actor "
            "JOIN identidad.profesional o ON o.id_profesional = b.id_profesional "
            "WHERE " + " AND ".join(condiciones) + " "
            "ORDER BY b.id_evento DESC LIMIT %(limite)s"
        )
        try:
            with self._conectar() as conexion:
                filas = conexion.execute(consulta, parametros).fetchall()
        except psycopg.Error as error:
            raise IntegracionNoConfigurada(
                "La bitacora de administracion no esta disponible."
            ) from error
        return [
            EntradaBitacora(
                id_evento=f["id_evento"],
                ocurrido_en=f["ocurrido_en"],
                accion=AccionBitacora(f["accion"]),
                id_actor=str(f["id_actor"]),
                actor_nombre=f["actor_nombre"],
                actor_rol=f["actor_rol"],
                id_profesional=str(f["id_profesional"]),
                profesional_nombre=f["profesional_nombre"],
                institucion=Institucion(f["establecimiento"]) if f["establecimiento"] else None,
                detalle=dict(f["detalle"] or {}),
            )
            for f in filas
        ]
