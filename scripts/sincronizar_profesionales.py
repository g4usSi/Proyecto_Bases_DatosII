"""Copia a Firestore el perfil de los profesionales de la Clinica Odontologica.

La identidad (correo, contrasena, permisos) sigue solo en PostgreSQL. Firestore
recibe nombres, apellidos, rol y estado para validar citas y mostrar la agenda.
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


def sincronizar(dsn: str, ids: list[str] | None = None) -> int:
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
    total = sincronizar(dsn)
    print(f"Profesionales de la clinica odontologica sincronizados: {total}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
