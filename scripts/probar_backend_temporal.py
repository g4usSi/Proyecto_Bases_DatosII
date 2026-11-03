"""Ejecuta pytest con PostgreSQL y MySQL temporales y todas las migraciones.

Usa el servidor local configurado y el rol limitado existente. No modifica .env ni
las tablas de hospital_general ni hospital_pediatrico. MongoDB usa fixtures sinteticas.
"""

import os
import re
import secrets
import subprocess
import sys
from contextlib import contextmanager
from uuid import uuid4

import psycopg
import pymysql
from dotenv import dotenv_values
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.core.config import PROJECT_ROOT
from tests.integration.conftest import ejecutar_script


@contextmanager
def mysql_temporal(config):
    nombre = "prueba_codex_" + uuid4().hex
    usuario = "prueba_" + uuid4().hex[:16]
    clave = secrets.token_urlsafe(24)
    assert re.fullmatch(r"prueba_codex_[0-9a-f]{32}", nombre)
    assert re.fullmatch(r"prueba_[0-9a-f]{16}", usuario)
    conexion = pymysql.connect(
        host="127.0.0.1",
        port=int(config["MYSQL_PORT"]),
        user="root",
        password=config["MYSQL_ROOT_PASSWORD"],
        autocommit=True,
    )
    try:
        with conexion.cursor() as cursor:
            cursor.execute("CREATE USER %s@'%%' IDENTIFIED BY %s", (usuario, clave))
        for ruta in sorted((PROJECT_ROOT / "database/mysql").glob("*.sql")):
            ejecutar_script(conexion, ruta, nombre, usuario)
        yield {
            "HISTORIALES_MYSQL_DATABASE": nombre,
            "HISTORIALES_MYSQL_USER": usuario,
            "HISTORIALES_MYSQL_PASSWORD": clave,
        }
    finally:
        with conexion.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{nombre}`")
            cursor.execute("DROP USER IF EXISTS %s@'%%'", (usuario,))
        conexion.close()


def main():
    config = dotenv_values(PROJECT_ROOT / ".env")
    admin_dsn = (
        os.environ.get("HISTORIALES_POSTGRES_ADMIN_DSN") or config["HISTORIALES_POSTGRES_ADMIN_DSN"]
    )
    app_dsn = os.environ.get("HISTORIALES_POSTGRES_DSN") or config["HISTORIALES_POSTGRES_DSN"]
    nombre = "prueba_codex_" + uuid4().hex
    assert re.fullmatch(r"prueba_codex_[0-9a-f]{32}", nombre)
    with psycopg.connect(admin_dsn, autocommit=True) as servidor:
        servidor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
        try:
            temporal_admin = make_conninfo(**(conninfo_to_dict(admin_dsn) | {"dbname": nombre}))
            with psycopg.connect(temporal_admin, autocommit=True) as conexion:
                for ruta in sorted((PROJECT_ROOT / "database/postgresql").glob("*.sql")):
                    # Las suites administrativas crean sus propios administradores unicos.
                    # El seed se verifica aparte en test_cuentas_demo.py, con otra BD temporal.
                    if ruta.name == "017_cuentas_demo.sql":
                        continue
                    contenido = ruta.read_text(encoding="utf-8")
                    if ruta.name.startswith("004_"):
                        contenido = "\n".join(
                            linea
                            for linea in contenido.splitlines()
                            if not linea.startswith(("\\getenv", "CREATE ROLE"))
                        )
                        contenido = contenido.replace(
                            "ON DATABASE hospital_general", f'ON DATABASE "{nombre}"'
                        )
                    conexion.execute(contenido)
                    print(f"Migracion aplicada: {ruta.name}", flush=True)
            entorno = os.environ | {
                "HISTORIALES_POSTGRES_ADMIN_DSN": temporal_admin,
                "HISTORIALES_POSTGRES_DSN": make_conninfo(
                    **(conninfo_to_dict(app_dsn) | {"dbname": nombre})
                ),
                "HISTORIALES_TEST_INTEGRATION": "1",
                "HISTORIALES_CUENTAS_DEMO": "false",
            }
            argumentos = sys.argv[1:] or [
                "tests/integration/test_hospital.py",
                "tests/integration/test_administracion.py",
            ]
            with mysql_temporal(config) as mysql_config:
                resultado = subprocess.run(
                    [sys.executable, "-m", "pytest", *argumentos],
                    env=entorno | mysql_config,
                    cwd=PROJECT_ROOT,
                )
            return resultado.returncode
        finally:
            # Solo el nombre generado y verificado arriba llega al DROP.
            servidor.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(nombre))
            )


if __name__ == "__main__":
    raise SystemExit(main())
