from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from app.application.errores import IntegracionNoConfigurada
from app.domain.cuenta import CuentaProfesional
from app.domain.institucion import Institucion

CONSULTA = """
SELECT p.id_profesional, p.correo, p.password_hash, p.establecimiento,
       p.version_token, p.bloqueado_hasta, (p.activo AND e.activo) AS activo,
       p.nombres, p.apellidos, p.rol, p.debe_cambiar_contrasena,
       COALESCE(array_agg(pp.permiso) FILTER (WHERE pp.permiso IS NOT NULL), '{}') AS permisos
FROM identidad.profesional p
JOIN identidad.establecimiento e ON e.codigo = p.establecimiento
LEFT JOIN identidad.profesional_permiso pp ON pp.id_profesional = p.id_profesional
WHERE {filtro}
GROUP BY p.id_profesional, e.activo
"""


class DirectorioPostgreSQL:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def _buscar(self, filtro: str, valor: object) -> CuentaProfesional | None:
        try:
            with psycopg.connect(self._dsn, connect_timeout=5, row_factory=dict_row) as conn:
                row = conn.execute(CONSULTA.replace("{filtro}", filtro), (valor,)).fetchone()
        except psycopg.Error as error:
            raise IntegracionNoConfigurada(
                "El directorio de profesionales no esta disponible."
            ) from error
        if row is None:
            return None
        return CuentaProfesional(
            str(row["id_profesional"]),
            row["correo"],
            row["password_hash"],
            Institucion(row["establecimiento"]),
            frozenset(row["permisos"]),
            row["version_token"],
            row["activo"],
            row["bloqueado_hasta"],
            row["nombres"],
            row["apellidos"],
            row["rol"],
            row["debe_cambiar_contrasena"],
        )

    def buscar_por_correo(self, correo: str) -> CuentaProfesional | None:
        return self._buscar("p.correo = %s", correo.strip().lower())

    def buscar_por_id(self, id_profesional: str) -> CuentaProfesional | None:
        try:
            identificador = UUID(id_profesional)
        except ValueError:
            return None
        return self._buscar("p.id_profesional = %s", identificador)

    def revocar_sesiones(self, id_profesional: str) -> None:
        try:
            with psycopg.connect(self._dsn, connect_timeout=5) as conn:
                conn.execute(
                    "UPDATE identidad.profesional SET version_token = version_token + 1 "
                    "WHERE id_profesional = %s",
                    (UUID(id_profesional),),
                )
        except psycopg.Error as error:
            raise IntegracionNoConfigurada(
                "El directorio de profesionales no esta disponible."
            ) from error

    def registrar_login(self, id_profesional: str, exitoso: bool) -> None:
        if exitoso:
            consulta = (
                "UPDATE identidad.profesional SET fallos_login=0, bloqueado_hasta=NULL "
                "WHERE id_profesional=%s"
            )
        else:
            consulta = """
            UPDATE identidad.profesional SET
              fallos_login = CASE WHEN bloqueado_hasta <= now() THEN 1 ELSE fallos_login + 1 END,
              bloqueado_hasta = CASE
                WHEN (CASE WHEN bloqueado_hasta <= now() THEN 1 ELSE fallos_login + 1 END) >= 5
                THEN now() + interval '15 minutes' ELSE NULL END
            WHERE id_profesional=%s
            """
        try:
            with psycopg.connect(self._dsn, connect_timeout=5) as conn:
                conn.execute(consulta, (UUID(id_profesional),))
        except psycopg.Error as error:
            raise IntegracionNoConfigurada("No se pudo actualizar el acceso central.") from error
