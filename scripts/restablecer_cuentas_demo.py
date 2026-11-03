"""Alinea las cinco cuentas administrativas con los accesos demo del README.

Operacion manual para la entrega: conserva IDs, permisos y datos, cambia correos y
contrasenas, desbloquea las cuentas y revoca sus sesiones. Nunca se ejecuta al arrancar.
"""

import os

import psycopg
from dotenv import dotenv_values

from app.bootstrap.cuentas_demo import CONTRASENA_DEMO, MIGRACION_DEMO, inicializar_cuentas_demo
from app.core.config import PROJECT_ROOT, Settings
from app.infrastructure.identity.cifrado import CifradorArgon2

CORREOS_DEMO = {
    None: "superadmin@demo.local",
    "hospital_general": "admin.hospital@demo.local",
    "centro_pediatrico": "admin.pediatria@demo.local",
    "laboratorio_clinico": "admin.laboratorio@demo.local",
    "clinica_odontologica": "admin.odontologia@demo.local",
}


def restablecer(dsn: str) -> None:
    with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as conexion:
        conexion.execute(MIGRACION_DEMO.read_text(encoding="utf-8"))
        with conexion.transaction():
            conexion.execute("SELECT pg_advisory_xact_lock(170017)")
            seleccionadas = []
            for alcance, correo in CORREOS_DEMO.items():
                rol = "superusuario" if alcance is None else "administrador"
                fila = conexion.execute(
                    "SELECT id_profesional FROM identidad.profesional "
                    "WHERE establecimiento IS NOT DISTINCT FROM %s AND rol=%s "
                    "AND eliminado_en IS NULL "
                    "ORDER BY activo DESC, creado_en, id_profesional LIMIT 1 FOR UPDATE",
                    (alcance, rol),
                ).fetchone()
                if fila is None:
                    raise ValueError(f"No hay cuenta recuperable para {correo}.")
                ocupada = conexion.execute(
                    "SELECT id_profesional FROM identidad.profesional WHERE correo=%s",
                    (correo,),
                ).fetchone()
                if ocupada and ocupada[0] != fila[0]:
                    raise ValueError(
                        f"El correo {correo} pertenece a otra cuenta; no se reemplazo."
                    )
                seleccionadas.append((fila[0], alcance, correo))
            cifrada = CifradorArgon2().cifrar(CONTRASENA_DEMO)
            for identificador, alcance, correo in seleccionadas:
                conexion.execute(
                    "UPDATE identidad.profesional SET correo=%s, password_hash=%s, activo=TRUE, "
                    "bloqueado_hasta=NULL, fallos_login=0, debe_cambiar_contrasena=FALSE, "
                    "version_token=version_token+1, actualizado_en=now() "
                    "WHERE id_profesional=%s",
                    (correo, cifrada, identificador),
                )
                conexion.execute(
                    "INSERT INTO identidad.bitacora_profesionales "
                    "(id_actor,id_profesional,establecimiento,accion,detalle) "
                    "VALUES (%s,%s,%s,'restablecer_contrasena',"
                    '\'{"origen":"restablecer_cuentas_demo"}\')',
                    (identificador, identificador, alcance),
                )


def main() -> None:
    settings = Settings()
    if settings.environment != "desarrollo":
        raise SystemExit(
            "Este comando de demostracion requiere HISTORIALES_ENVIRONMENT=desarrollo."
        )
    config = dotenv_values(PROJECT_ROOT / ".env")
    dsn = os.environ.get("HISTORIALES_POSTGRES_ADMIN_DSN") or config.get(
        "HISTORIALES_POSTGRES_ADMIN_DSN"
    )
    if not dsn:
        raise SystemExit(
            "Falta HISTORIALES_POSTGRES_ADMIN_DSN. Ejecuta scripts.configurar_desarrollo."
        )
    try:
        restablecer(dsn)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    except psycopg.Error as error:
        raise SystemExit(
            "No se restablecieron los accesos. Revisa PostgreSQL y sus migraciones."
        ) from error
    print(
        "Cinco accesos demo restablecidos. IDs y datos conservados; sesiones anteriores revocadas."
    )
    inicializar_cuentas_demo(settings)


if __name__ == "__main__":
    main()
