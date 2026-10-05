"""Alta administrativa de profesionales; la API no permite autorregistro."""

import argparse
import getpass
import os
from uuid import uuid4

import psycopg
from dotenv import dotenv_values
from pwdlib import PasswordHash

from app.core.config import PROJECT_ROOT
from app.domain.institucion import Institucion


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--correo", required=True)
    parser.add_argument("--nombres", required=True)
    parser.add_argument("--apellidos", required=True)
    parser.add_argument(
        "--institucion", required=True, choices=[item.value for item in Institucion]
    )
    parser.add_argument(
        "--rol", required=True, choices=["medico", "enfermeria", "laboratorista", "odontologo"]
    )
    parser.add_argument(
        "--permiso",
        action="append",
        default=[],
        help="Repetir por permiso; defecto solo pacientes:leer",
    )
    args = parser.parse_args()
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
            for permiso in set(args.permiso or ["pacientes:leer"]):
                conn.execute(
                    "INSERT INTO identidad.profesional_permiso VALUES (%s,%s)",
                    (identificador, permiso),
                )
    except psycopg.errors.UniqueViolation:
        parser.error("Ese correo ya tiene una cuenta; no se modifico.")
    except psycopg.errors.ForeignKeyViolation:
        parser.error("Institucion o permiso desconocido; se revirtio el alta.")
    except psycopg.Error:
        parser.error("No se pudo crear el profesional. Revisa conexiones y datos requeridos.")
    print(f"Profesional creado: {identificador}. Establecimiento: {args.institucion}.")
    print("Vincular este UUID al registro clinico local cuando se habiliten escrituras.")


if __name__ == "__main__":
    main()
