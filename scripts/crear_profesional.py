"""Alta administrativa de profesionales; la API no permite autorregistro."""

import argparse
import getpass
import os
from uuid import uuid4

import psycopg
from dotenv import dotenv_values
from pwdlib import PasswordHash

from app.core.config import PROJECT_ROOT
from app.domain import permisos
from app.domain.institucion import Institucion

ROLES = ["medico", "enfermeria", "laboratorista", "odontologo", "secretaria"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--correo", required=True)
    parser.add_argument("--nombres", required=True)
    parser.add_argument("--apellidos", required=True)
    parser.add_argument(
        "--institucion", required=True, choices=[item.value for item in Institucion]
    )
    parser.add_argument("--rol", required=True, choices=ROLES)
    parser.add_argument(
        "--permiso",
        action="append",
        default=[],
        help=(
            "Repetir por permiso. Por defecto: pacientes:leer; secretaria: pacientes:leer, "
            "pacientes:registrar, citas:leer y citas:gestionar."
        ),
    )
    args = parser.parse_args()
    elegidos = set(args.permiso) or set(
        permisos.PERMISOS_POR_ROL.get(args.rol, permisos.PERMISOS_POR_DEFECTO)
    )
    if args.rol == "secretaria" and args.institucion != permisos.INSTITUCION_DE_SECRETARIA:
        parser.error("El rol secretaria solo existe en la clinica_odontologica.")
    if args.rol == "secretaria" and elegidos & permisos.PERMISOS_VEDADOS_SECRETARIA:
        parser.error(
            "Una secretaria no puede tener permisos clinicos ni archivar historiales: "
            + ", ".join(sorted(elegidos & permisos.PERMISOS_VEDADOS_SECRETARIA))
        )
    correo = args.correo.strip().lower()
    if "@" not in correo or any(char.isspace() for char in correo):
        parser.error("Correo invalido.")
    password = getpass.getpass("Contrasena (minimo 12 caracteres): ")
    if not 12 <= len(password) <= 1024 or password != getpass.getpass("Repetir contrasena: "):
        parser.error("La contrasena es demasiado corta o la confirmacion no coincide.")
    config = dotenv_values(PROJECT_ROOT / ".env")
    dsn = os.environ.get("HISTORIALES_POSTGRES_ADMIN_DSN") or config.get(
        "HISTORIALES_POSTGRES_ADMIN_DSN"
    )
    if not dsn:
        parser.error("Falta HISTORIALES_POSTGRES_ADMIN_DSN. Ejecuta configurar_desarrollo.")
    identificador = uuid4()
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute(
                "INSERT INTO identidad.profesional "
                "(id_profesional, correo, nombres, apellidos, password_hash, establecimiento, rol) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    identificador,
                    correo,
                    args.nombres,
                    args.apellidos,
                    PasswordHash.recommended().hash(password),
                    args.institucion,
                    args.rol,
                ),
            )
            for permiso in sorted(elegidos):
                conn.execute(
                    "INSERT INTO identidad.profesional_permiso VALUES (%s,%s)",
                    (identificador, permiso),
                )
            if args.institucion == Institucion.HOSPITAL_GENERAL:
                # Misma base y misma transaccion: la cuenta y su perfil nacen juntos.
                from scripts.sincronizar_profesionales import sincronizar_hospital

                sincronizar_hospital(conn, [str(identificador)])
    except psycopg.errors.UniqueViolation:
        parser.error("Ese correo ya tiene una cuenta; no se modifico.")
    except psycopg.errors.CheckViolation:
        parser.error(
            "La base rechazo el rol o los permisos. Aplica 006 y 007 (database/postgresql) "
            "si la base se creo antes de agregar el rol secretaria."
        )
    except psycopg.errors.ForeignKeyViolation:
        parser.error("Institucion o permiso desconocido; se revirtio el alta.")
    except psycopg.Error:
        parser.error("No se pudo crear el profesional. Revisa conexiones y datos requeridos.")
    print(f"Profesional creado: {identificador}. Establecimiento: {args.institucion}.")
    print(f"Permisos: {', '.join(sorted(elegidos))}.")
    if args.institucion == Institucion.CLINICA_ODONTOLOGICA:
        # Perfil local en Firestore (sin correo ni contrasena). No es una transaccion entre
        # motores: si falla, PostgreSQL conserva la cuenta y se puede repetir la sincronizacion.
        from scripts.sincronizar_profesionales import sincronizar

        try:
            sincronizar(dsn, [str(identificador)])
            print("Perfil creado en Firestore (coleccion profesionales).")
        except Exception as error:  # noqa: BLE001 - se informa y se puede reintentar
            print(f"Aviso: no se creo el perfil en Firestore ({error}).")
            print("Reintentar con: python -m scripts.sincronizar_profesionales")
    elif args.institucion == Institucion.HOSPITAL_GENERAL:
        print("Vinculado a personal_medico del Hospital General.")
    elif args.institucion == Institucion.CENTRO_PEDIATRICO:
        # Otra base: si falla, PostgreSQL conserva la cuenta y se puede repetir la sincronizacion.
        from scripts.sincronizar_profesionales import sincronizar_centro_pediatrico

        try:
            sincronizar_centro_pediatrico(dsn, [str(identificador)])
            print("Vinculado a la tabla medico del Centro Pediatrico.")
        except Exception as error:  # noqa: BLE001 - se informa y se puede reintentar
            print(f"Aviso: no se vinculo en MySQL ({error}).")
            print("Reintentar con: python -m scripts.sincronizar_profesionales")
    elif args.institucion == Institucion.LABORATORIO_CLINICO:
        # Otra base: si falla, PostgreSQL conserva la cuenta y se puede repetir la sincronizacion.
        from scripts.sincronizar_profesionales import sincronizar_laboratorio

        try:
            sincronizar_laboratorio(dsn, [str(identificador)])
            print("Perfil creado en MongoDB (coleccion profesionales).")
        except Exception as error:  # noqa: BLE001 - se informa y se puede reintentar
            print(f"Aviso: no se creo el perfil en MongoDB ({error}).")
            print("Reintentar con: python -m scripts.sincronizar_profesionales")


if __name__ == "__main__":
    main()
