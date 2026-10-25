"""Vincula las cuentas centrales con el personal clinico de cada institucion.

La identidad (correo, contrasena, permisos) vive solo en PostgreSQL. Cada motor
recibe un perfil sin credenciales (nombres, apellidos, rol, estado):

- Hospital General: tabla personal_medico (misma base que la identidad, atomico).
- Centro Pediatrico: tabla medico de MySQL (con la cuenta administrativa de MYSQL_ROOT_PASSWORD).
- Laboratorio Clinico: coleccion `profesionales` de MongoDB (cuenta de MONGO_ROOT_PASSWORD).
- Clinica Odontologica: coleccion `profesionales` de Firestore.

Es idempotente: se puede ejecutar cuantas veces se quiera.

    python -m scripts.sincronizar_profesionales
"""

import os
import sys

import psycopg
import pymysql
from dotenv import dotenv_values
from google.cloud import firestore
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.core.config import PROJECT_ROOT, Settings
from app.infrastructure.persistence.firestore.cliente import crear_cliente_firestore
from app.infrastructure.persistence.firestore.unidad import COLECCION_PROFESIONALES


def sincronizar_hospital(conexion: psycopg.Connection, ids: list[str] | None = None) -> int:
    """Crea o actualiza personal_medico a partir de identidad.profesional (misma base)."""
    filtro = " AND p.id_profesional::text = ANY(%s)" if ids else ""
    cursor = conexion.execute(
        "INSERT INTO personal_medico (nombres, apellidos, rol, estado, id_profesional_central) "
        "SELECT p.nombres, p.apellidos, "
        "  CASE p.rol WHEN 'medico' THEN 'Medico' WHEN 'enfermeria' THEN 'Enfermero' "
        "             WHEN 'laboratorista' THEN 'Tecnico' WHEN 'odontologo' THEN 'Medico' "
        "             ELSE 'Administrativo' END, "
        "  CASE WHEN p.activo THEN 'Activo' ELSE 'Inactivo' END, p.id_profesional "
        "FROM identidad.profesional p WHERE p.establecimiento = 'hospital_general'" + filtro + " "
        "ON CONFLICT (id_profesional_central) DO UPDATE SET "
        "  nombres = EXCLUDED.nombres, apellidos = EXCLUDED.apellidos, rol = EXCLUDED.rol, "
        # No se pisa un 'Suspendido' puesto por el hospital mientras la cuenta siga activa.
        "  estado = CASE WHEN EXCLUDED.estado = 'Inactivo' THEN 'Inactivo' "
        "                WHEN personal_medico.estado = 'Inactivo' THEN 'Activo' "
        "                ELSE personal_medico.estado END",
        (ids,) if ids else (),
    )
    return cursor.rowcount


def sincronizar_centro_pediatrico(
    dsn: str, ids: list[str] | None = None, conexion_mysql: pymysql.Connection | None = None
) -> int:
    """MySQL (Centro Pediatrico): crea o actualiza `medico` a partir de la identidad central.

    El codigo de colegiado real lo completa el hospital: aqui se usa uno provisional unico
    (PEND-<uuid>) que nunca se sobrescribe en una sincronizacion posterior.
    """
    consulta = (
        "SELECT id_profesional::text, nombres, apellidos, activo FROM identidad.profesional "
        "WHERE establecimiento = 'centro_pediatrico'"
    )
    parametros: tuple = ()
    if ids:
        consulta += " AND id_profesional::text = ANY(%s)"
        parametros = (ids,)
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        filas = conn.execute(consulta, parametros).fetchall()
    if not filas:
        return 0
    propia = conexion_mysql is None
    if propia:
        conexion_mysql = _conectar_mysql_admin()
    try:
        with conexion_mysql.cursor() as cursor:
            for id_profesional, nombres, apellidos, activo in filas:
                cursor.execute(
                    "INSERT INTO medico "
                    "(id_profesional_central, nombre, apellido, colegiado, activo) "
                    "VALUES (%s, %s, %s, %s, %s) AS nuevo "
                    "ON DUPLICATE KEY UPDATE nombre = nuevo.nombre, apellido = nuevo.apellido, "
                    "activo = nuevo.activo",
                    (id_profesional, nombres, apellidos, f"PEND-{id_profesional}", activo),
                )
        conexion_mysql.commit()
    finally:
        if propia:
            conexion_mysql.close()
    return len(filas)


def sincronizar_laboratorio(dsn: str, ids: list[str] | None = None, coleccion=None) -> int:
    """MongoDB (Laboratorio Clinico): crea o actualiza la coleccion `profesionales`."""
    consulta = (
        "SELECT id_profesional::text, nombres, apellidos, activo, rol FROM identidad.profesional "
        "WHERE establecimiento = 'laboratorio_clinico'"
    )
    parametros: tuple = ()
    if ids:
        consulta += " AND id_profesional::text = ANY(%s)"
        parametros = (ids,)
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        filas = conn.execute(consulta, parametros).fetchall()
    if not filas:
        return 0
    cliente = None
    if coleccion is None:
        cliente, coleccion = _conectar_mongo_admin()
    try:
        for id_profesional, nombres, apellidos, activo, rol in filas:
            coleccion.update_one(
                {"id_profesional_central": id_profesional},
                {
                    "$set": {
                        "nombres": nombres,
                        "apellidos": apellidos,
                        "activo": activo,
                        "rol": rol,
                    }
                },
                upsert=True,
            )
    finally:
        if cliente is not None:
            cliente.close()
    return len(filas)


def _conectar_mongo_admin():
    config = dotenv_values(PROJECT_ROOT / ".env")
    clave = os.environ.get("MONGO_ROOT_PASSWORD") or config.get("MONGO_ROOT_PASSWORD")
    if not clave:
        raise RuntimeError("Falta MONGO_ROOT_PASSWORD en .env (cuenta administrativa de MongoDB).")
    puerto = int(os.environ.get("MONGO_PORT") or config.get("MONGO_PORT") or 27018)
    cliente = MongoClient(
        host="127.0.0.1",
        port=puerto,
        username="historiales_admin",
        password=clave,
        authSource="admin",
        serverSelectionTimeoutMS=5000,
    )
    return cliente, cliente[Settings().mongodb_database].profesionales


def _conectar_mysql_admin() -> pymysql.Connection:
    config = dotenv_values(PROJECT_ROOT / ".env")
    clave = os.environ.get("MYSQL_ROOT_PASSWORD") or config.get("MYSQL_ROOT_PASSWORD")
    if not clave:
        raise RuntimeError("Falta MYSQL_ROOT_PASSWORD en .env (cuenta administrativa de MySQL).")
    puerto = int(os.environ.get("MYSQL_PORT") or config.get("MYSQL_PORT") or 3307)
    try:
        return pymysql.connect(
            host="127.0.0.1",
            port=puerto,
            user="root",
            password=clave,
            database=Settings().mysql_database,
            charset="utf8mb4",
            connect_timeout=5,
        )
    except pymysql.MySQLError as error:
        raise RuntimeError(f"No se pudo conectar a MySQL ({error.args[0]}).") from error


def sincronizar(dsn: str, ids: list[str] | None = None) -> int:
    """Firestore (Clinica Odontologica)."""
    settings = Settings()
    ruta = settings.firestore_credentials
    if ruta is None or not ruta.is_file():
        raise RuntimeError("Falta la clave de Firebase (.secrets/firebase-adminsdk.json).")
    consulta = (
        "SELECT id_profesional::text, nombres, apellidos, rol, activo "
        "FROM identidad.profesional WHERE establecimiento = 'clinica_odontologica'"
    )
    parametros: tuple = ()
    if ids:
        consulta += " AND id_profesional::text = ANY(%s)"
        parametros = (ids,)
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        filas = conn.execute(consulta, parametros).fetchall()
    cliente, cerrar = crear_cliente_firestore(
        ruta, settings.firestore_project_id, settings.firestore_database
    )
    try:
        lote = cliente.batch()
        for id_profesional, nombres, apellidos, rol, activo in filas:
            lote.set(
                cliente.collection(COLECCION_PROFESIONALES).document(id_profesional),
                {
                    "nombres": nombres,
                    "apellidos": apellidos,
                    "rol": rol,
                    "activo": activo,
                    "sincronizado_en": firestore.SERVER_TIMESTAMP,
                },
            )
        if filas:
            lote.commit(timeout=15)
    finally:
        cerrar()
    return len(filas)


def main() -> int:
    config = dotenv_values(PROJECT_ROOT / ".env")
    dsn = os.environ.get("HISTORIALES_POSTGRES_ADMIN_DSN") or config.get(
        "HISTORIALES_POSTGRES_ADMIN_DSN"
    )
    if not dsn:
        print("Falta HISTORIALES_POSTGRES_ADMIN_DSN. Ejecuta configurar_desarrollo.")
        return 1
    with psycopg.connect(dsn, connect_timeout=5) as conexion:
        total_hospital = sincronizar_hospital(conexion)
    print(f"Hospital General: {total_hospital} profesionales vinculados.")
    try:
        total_pediatrico = sincronizar_centro_pediatrico(dsn)
        print(f"Centro Pediatrico: {total_pediatrico} profesionales sincronizados.")
    except RuntimeError as error:
        print(f"Centro Pediatrico: omitido ({error})")
    try:
        total_lab = sincronizar_laboratorio(dsn)
        print(f"Laboratorio Clinico: {total_lab} profesionales sincronizados.")
    except (RuntimeError, PyMongoError) as error:
        print(f"Laboratorio Clinico: omitido ({error})")
    try:
        total = sincronizar(dsn)
        print(f"Clinica Odontologica: {total} profesionales sincronizados.")
    except RuntimeError as error:
        print(f"Clinica Odontologica: omitida ({error})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
