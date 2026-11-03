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

ROLES = [
    "medico",
    "enfermeria",
    "laboratorista",
    "odontologo",
    "secretaria",
    "administrador",
    "superusuario",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--correo", required=True)
    parser.add_argument("--nombres", required=True)
    parser.add_argument("--apellidos", required=True)
    parser.add_argument(
        "--institucion", "--establecimiento", choices=[item.value for item in Institucion]
    )
    parser.add_argument("--rol", required=True, choices=ROLES)
    parser.add_argument(
        "--permiso",
        action="append",
        default=[],
        help=(
            "Repetir por permiso. Por defecto: pacientes:leer; secretaria: pacientes:leer, "
            "pacientes:registrar, citas:leer y citas:gestionar; laboratorista: pacientes:leer, "
            "laboratorio:resultados y laboratorio:validar; odontologo: pacientes:leer, "
            "pacientes:registrar, historiales:leer, consultas:registrar, citas:leer y "
            "citas:gestionar; administrador: profesionales:administrar (unico permiso posible)."
        ),
    )
    args = parser.parse_args()
    if (args.rol == "superusuario") != (args.institucion is None):
        parser.error("El superusuario no tiene institucion; los demas roles deben indicar una.")
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
    if args.rol == "administrador" and elegidos != {permisos.PROFESIONALES_ADMINISTRAR}:
        parser.error(
            "La cuenta de administracion tiene solo profesionales:administrar (sin permisos "
            "clinicos). Omite --permiso."
        )
    if args.rol == "superusuario" and elegidos != permisos.PERMISOS_POR_ROL["superusuario"]:
        parser.error("El superusuario tiene solo plataforma:administrar y pagos:ver.")
    if args.rol != "superusuario" and permisos.PLATAFORMA_ADMINISTRAR in elegidos:
        parser.error("plataforma:administrar es exclusivo del superusuario.")
    if args.rol != "administrador" and permisos.PROFESIONALES_ADMINISTRAR in elegidos:
        parser.error("profesionales:administrar es exclusivo del rol administrador.")
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
                "(id_profesional, correo, nombres, apellidos, password_hash, establecimiento, "
                "rol, debe_cambiar_contrasena) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE)",
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
            if args.institucion == Institucion.HOSPITAL_GENERAL and args.rol != "administrador":
                # Misma base y misma transaccion: la cuenta y su perfil nacen juntos.
                from scripts.sincronizar_profesionales import sincronizar_hospital

                sincronizar_hospital(conn, [str(identificador)])
    except psycopg.errors.UniqueViolation:
        parser.error("El correo ya existe o ya hay una cuenta de administracion para ese alcance.")
    except psycopg.errors.CheckViolation:
        parser.error(
            "La base rechazo el rol o los permisos. Aplica las migraciones de "
            "database/postgresql hasta 015 si la base se creo antes."
        )
    except psycopg.errors.ForeignKeyViolation:
        parser.error("Institucion o permiso desconocido; se revirtio el alta.")
    except psycopg.Error:
        parser.error("No se pudo crear el profesional. Revisa conexiones y datos requeridos.")
    print(f"Profesional creado: {identificador}. Establecimiento: {args.institucion}.")
    print(f"Permisos: {', '.join(sorted(elegidos))}.")
    if args.rol == "superusuario":
        print("Cuenta de plataforma: administra las cuatro instituciones, sin acceso clinico.")
    elif args.rol == "administrador":
        print("Cuenta de administracion: gestiona el personal de su institucion desde la API.")
    elif args.institucion == Institucion.CLINICA_ODONTOLOGICA:
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
