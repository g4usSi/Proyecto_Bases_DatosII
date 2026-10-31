"""Alta administrativa de profesionales; la API no permite autorregistro.

Tambien crea el superusuario de plataforma (uno solo, sin --institucion) y lo recupera si
pierde el acceso:

    python -m scripts.crear_profesional --correo su@example.com --nombres "Sara" \
        --apellidos "Admin" --rol superusuario
    python -m scripts.crear_profesional --restablecer-superusuario
"""

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


def _dsn(parser: argparse.ArgumentParser) -> str:
    config = dotenv_values(PROJECT_ROOT / ".env")
    dsn = os.environ.get("HISTORIALES_POSTGRES_ADMIN_DSN") or config.get(
        "HISTORIALES_POSTGRES_ADMIN_DSN"
    )
    if not dsn:
        parser.error("Falta HISTORIALES_POSTGRES_ADMIN_DSN. Ejecuta configurar_desarrollo.")
    return dsn


def _pedir_contrasena(parser: argparse.ArgumentParser) -> str:
    password = getpass.getpass("Contrasena (minimo 12 caracteres): ")
    if not 12 <= len(password) <= 1024 or password != getpass.getpass("Repetir contrasena: "):
        parser.error("La contrasena es demasiado corta o la confirmacion no coincide.")
    return password


def restablecer_superusuario(parser: argparse.ArgumentParser) -> None:
    """Recupera el acceso del superusuario: contrasena nueva (debe cambiarla al entrar),
    desbloqueo y cierre de sus sesiones. Queda en la bitacora de administracion."""
    dsn = _dsn(parser)
    password = _pedir_contrasena(parser)
    with psycopg.connect(dsn, connect_timeout=5) as conn:
        fila = conn.execute(
            "UPDATE identidad.profesional SET password_hash = %s, debe_cambiar_contrasena = TRUE, "
            "activo = TRUE, bloqueado_hasta = NULL, fallos_login = 0, "
            "version_token = version_token + 1, actualizado_en = now() "
            "WHERE rol = 'superusuario' AND eliminado_en IS NULL RETURNING id_profesional, correo",
            (PasswordHash.recommended().hash(password),),
        ).fetchone()
        if fila is None:
            parser.error("No existe un superusuario. Crealo con --rol superusuario.")
        conn.execute(
            "INSERT INTO identidad.bitacora_profesionales "
            "(id_actor, id_profesional, establecimiento, accion, detalle) "
            "VALUES (%s, %s, NULL, 'restablecer_contrasena', '{\"via\": \"script\"}')",
            (fila[0], fila[0]),
        )
    print(f"Acceso del superusuario {fila[1]} restablecido; debera elegir otra contrasena.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--restablecer-superusuario",
        action="store_true",
        help="Recupera el acceso del superusuario (contrasena nueva y desbloqueo).",
    )
    parser.add_argument("--correo")
    parser.add_argument("--nombres")
    parser.add_argument("--apellidos")
    parser.add_argument(
        "--institucion",
        choices=[item.value for item in Institucion],
        help="Obligatoria salvo para --rol superusuario (que no pertenece a una entidad).",
    )
    parser.add_argument("--rol", choices=ROLES)
    parser.add_argument(
        "--permiso",
        action="append",
        default=[],
        help=(
            "Repetir por permiso. Por defecto: pacientes:leer; secretaria: pacientes:leer, "
            "pacientes:registrar, citas:leer y citas:gestionar; laboratorista: pacientes:leer, "
            "laboratorio:resultados y laboratorio:validar; administrador: "
            "profesionales:administrar (unico permiso posible); superusuario: "
            "plataforma:administrar y pagos:ver (fijos)."
        ),
    )
    args = parser.parse_args()
    if args.restablecer_superusuario:
        restablecer_superusuario(parser)
        return
    faltan = [n for n in ("correo", "nombres", "apellidos", "rol") if not getattr(args, n)]
    if faltan:
        parser.error("Faltan: " + ", ".join("--" + n for n in faltan))
    superusuario = args.rol == "superusuario"
    if superusuario and args.institucion:
        parser.error("El superusuario no pertenece a una institucion: omite --institucion.")
    if not superusuario and not args.institucion:
        parser.error("Falta --institucion.")
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
    if args.rol != "administrador" and permisos.PROFESIONALES_ADMINISTRAR in elegidos:
        parser.error("profesionales:administrar es exclusivo del rol administrador.")
    if superusuario and elegidos != permisos.PERMISOS_POR_ROL["superusuario"]:
        parser.error(
            "El superusuario tiene solo plataforma:administrar y pagos:ver. Omite --permiso."
        )
    if not superusuario and permisos.PLATAFORMA_ADMINISTRAR in elegidos:
        parser.error("plataforma:administrar es exclusivo del superusuario.")
    correo = args.correo.strip().lower()
    if "@" not in correo or any(char.isspace() for char in correo):
        parser.error("Correo invalido.")
    password = _pedir_contrasena(parser)
    dsn = _dsn(parser)
    identificador = uuid4()
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            conn.execute(
                "INSERT INTO identidad.profesional "
                "(id_profesional, correo, nombres, apellidos, password_hash, establecimiento, rol, "
                "debe_cambiar_contrasena) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    identificador,
                    correo,
                    args.nombres,
                    args.apellidos,
                    PasswordHash.recommended().hash(password),
                    args.institucion,
                    args.rol,
                    # Cuenta de alto valor: elige su propia contrasena en el primer ingreso.
                    superusuario,
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
    except psycopg.errors.UniqueViolation as error:
        if error.diag.constraint_name == "ux_un_superusuario":
            parser.error(
                "Ya existe un superusuario. Para recuperar su acceso usa "
                "--restablecer-superusuario."
            )
        if error.diag.constraint_name == "ux_un_admin_por_entidad":
            parser.error("Esa institucion ya tiene un administrador activo.")
        parser.error("Ese correo ya tiene una cuenta; no se modifico.")
    except psycopg.errors.CheckViolation:
        parser.error(
            "La base rechazo el rol o los permisos. Aplica las migraciones de "
            "database/postgresql (006, 007, 012 y 015) si la base se creo antes."
        )
    except psycopg.errors.ForeignKeyViolation:
        parser.error("Institucion o permiso desconocido; se revirtio el alta.")
    except psycopg.Error:
        parser.error("No se pudo crear el profesional. Revisa conexiones y datos requeridos.")
    print(
        f"Profesional creado: {identificador}. "
        f"Establecimiento: {args.institucion or 'ninguno (plataforma)'}."
    )
    print(f"Permisos: {', '.join(sorted(elegidos))}.")
    if superusuario:
        print("Superusuario de plataforma: debera elegir su contrasena al iniciar sesion.")
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
