"""Vincula las cuentas centrales con el personal clinico de cada institucion.

La identidad (correo, contrasena, permisos) vive solo en PostgreSQL. Cada motor
recibe un perfil sin credenciales (nombres, apellidos, rol, estado):

- Hospital General: tabla personal_medico (misma base que la identidad, atomico).
- Clinica Odontologica: coleccion `profesionales` de Firestore.

Es idempotente: se puede ejecutar cuantas veces se quiera.

    python -m scripts.sincronizar_profesionales
"""

import os
import sys

import psycopg
from dotenv import dotenv_values
from google.cloud import firestore

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
        total = sincronizar(dsn)
        print(f"Clinica Odontologica: {total} profesionales sincronizados.")
    except RuntimeError as error:
        print(f"Clinica Odontologica: omitida ({error})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
