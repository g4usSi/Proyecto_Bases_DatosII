"""Administracion de cuentas en la identidad central (PostgreSQL, esquema identidad).

Cada operacion abre su conexion y hace UNA transaccion: el cambio de la cuenta y su
evento en identidad.bitacora_profesionales se guardan juntos o no se guarda nada.
Las cuentas de administracion no se listan ni se modifican por esta via.
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
    CambiosProfesional,
    EstadoCuenta,
    FichaProfesional,
    NuevoProfesional,
    ProfesionalAgenda,
)
from app.domain.errores import ConflictoEstado, DatosInvalidos, RegistroNoEncontrado
from app.domain.institucion import Institucion

# Bloqueo puesto por la administracion (indefinido). El bloqueo por intentos fallidos
# usa una fecha cercana; restablecer la contrasena solo quita ese ultimo.
BLOQUEO_ADMINISTRATIVO = datetime(9999, 12, 31, tzinfo=UTC)

_ESTADO_SQL = (
    "CASE WHEN NOT p.activo THEN 'inactiva' "
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
WHERE p.establecimiento = %(institucion)s AND p.rol <> '{ROL_ADMINISTRADOR}' {{filtro}}
GROUP BY p.id_profesional, d.descripcion
"""


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
        institucion=Institucion(fila["establecimiento"]),
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
        self, conexion: psycopg.Connection, institucion: Institucion, id_profesional: UUID
    ) -> FichaProfesional | None:
        fila = conexion.execute(
            _FICHA.replace("{filtro}", "AND p.id_profesional = %(id)s"),
            {"institucion": institucion.value, "id": id_profesional},
        ).fetchone()
        return _ficha(fila) if fila else None

    @staticmethod
    def _bitacora(
        conexion: psycopg.Connection,
        id_actor: str,
        id_profesional: UUID,
        institucion: str,
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
                ficha = self._leer(conexion, institucion, identificador)
        except psycopg.errors.UniqueViolation as error:
            raise ConflictoEstado("Ya existe una cuenta con ese correo.") from error
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
        institucion: Institucion,
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
                actual = conexion.execute(
                    "SELECT rol, activo, bloqueado_hasta, id_departamento, nombres, apellidos "
                    "FROM identidad.profesional WHERE id_profesional = %s "
                    "AND establecimiento = %s AND rol <> %s FOR UPDATE",
                    (identificador, institucion.value, ROL_ADMINISTRADOR),
                ).fetchone()
                if actual is None:
                    raise RegistroNoEncontrado("El profesional no existe en tu institucion.")
                antes = self._leer(conexion, institucion, identificador)
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
                        conexion, id_actor, identificador, institucion.value, "cambio", detalle
                    )
                ficha = self._leer(conexion, institucion, identificador)
        except (RegistroNoEncontrado, DatosInvalidos):
            raise
        except psycopg.errors.ForeignKeyViolation as error:
            raise DatosInvalidos("El area (departamento) o un permiso no existe.") from error
        except psycopg.errors.CheckViolation as error:
            raise DatosInvalidos("La base rechazo el area o los permisos.") from error
        except psycopg.Error as error:
            raise IntegracionNoConfigurada("No se pudo actualizar la cuenta.") from error
        assert ficha is not None
        return ficha

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
        institucion: Institucion,
        rol: str | None = None,
        id_departamento: int | None = None,
        estado: EstadoCuenta | None = None,
        limite: int = 200,
    ) -> list[FichaProfesional]:
        filtros = []
        parametros: dict[str, Any] = {"institucion": institucion.value, "limite": limite}
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
            _FICHA.replace("{filtro}", " ".join(filtros))
            + " ORDER BY p.apellidos, p.nombres, p.id_profesional LIMIT %(limite)s"
        )
        try:
            with self._conectar() as conexion:
                filas = conexion.execute(consulta, parametros).fetchall()
        except psycopg.Error as error:
            raise IntegracionNoConfigurada(
                "El directorio de profesionales no esta disponible."
            ) from error
        return [_ficha(f) for f in filas]

    def obtener(self, institucion: Institucion, id_profesional: str) -> FichaProfesional | None:
        identificador = _uuid(id_profesional)
        if identificador is None:
            return None
        try:
            with self._conectar() as conexion:
                return self._leer(conexion, institucion, identificador)
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
