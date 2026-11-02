"""Recupera la unica cuenta de plataforma desde una conexion administrativa local."""

import getpass
import os

import psycopg
from dotenv import dotenv_values
from pwdlib import PasswordHash

from app.core.config import PROJECT_ROOT
from app.domain.administracion import validar_contrasena


def main():
    clave = getpass.getpass("Nueva contrasena del superusuario: ")
    validar_contrasena(clave)
    if clave != getpass.getpass("Repetir contrasena: "):
        raise SystemExit("La confirmacion no coincide.")
    config = dotenv_values(PROJECT_ROOT / ".env")
    dsn = os.environ.get("HISTORIALES_POSTGRES_ADMIN_DSN") or config.get(
        "HISTORIALES_POSTGRES_ADMIN_DSN"
    )
    if not dsn:
        raise SystemExit("Falta HISTORIALES_POSTGRES_ADMIN_DSN.")
    with psycopg.connect(dsn, connect_timeout=5) as conexion:
        fila = conexion.execute(
            "UPDATE identidad.profesional SET password_hash = %s, activo = TRUE, "
            "bloqueado_hasta = NULL, fallos_login = 0, debe_cambiar_contrasena = TRUE, "
            "version_token = version_token + 1, actualizado_en = now() "
            "WHERE rol = 'superusuario' AND eliminado_en IS NULL RETURNING id_profesional",
            (PasswordHash.recommended().hash(clave),),
        ).fetchone()
        if fila is None:
            raise SystemExit("No existe un superusuario; crealo con scripts.crear_profesional.")
        conexion.execute(
            "INSERT INTO identidad.bitacora_profesionales "
            "(id_actor,id_profesional,establecimiento,accion,detalle) "
            "VALUES (%s,%s,NULL,'restablecer_contrasena','{\"origen\":\"recuperacion_local\"}')",
            (fila[0], fila[0]),
        )
    print("Acceso recuperado; las sesiones anteriores quedaron revocadas.")


if __name__ == "__main__":
    main()
