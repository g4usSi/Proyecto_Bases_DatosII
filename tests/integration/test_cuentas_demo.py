"""Seed y login contra una base PostgreSQL nueva y aislada en cada prueba."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.bootstrap.cuentas_demo import CONTRASENA_DEMO, MIGRACION_DEMO, inicializar_cuentas_demo
from app.core.config import PROJECT_ROOT, Settings
from app.domain.permisos import PERMISOS_POR_ROL
from app.infrastructure.identity.cifrado import CifradorArgon2
from app.main import create_app


@pytest.fixture
def demo(config_local):
    nombre = "prueba_demo_" + uuid4().hex
    admin_dsn = config_local["HISTORIALES_POSTGRES_ADMIN_DSN"]
    with psycopg.connect(admin_dsn, autocommit=True) as servidor:
        servidor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
        try:
            dsn = make_conninfo(**(conninfo_to_dict(admin_dsn) | {"dbname": nombre}))
            with psycopg.connect(dsn, autocommit=True) as conexion:
                for ruta in sorted((PROJECT_ROOT / "database/postgresql").glob("*.sql")):
                    if ruta == MIGRACION_DEMO:
                        continue
                    contenido = ruta.read_text(encoding="utf-8")
                    if ruta.name.startswith("004_"):
                        contenido = "\n".join(
                            linea
                            for linea in contenido.splitlines()
                            if not linea.startswith(("\\getenv", "CREATE ROLE"))
                        ).replace("ON DATABASE hospital_general", f'ON DATABASE "{nombre}"')
                    conexion.execute(contenido)
                settings = Settings(
                    _env_file=None,
                    environment="desarrollo",
                    cuentas_demo=True,
                    postgres_dsn=make_conninfo(
                        **(
                            conninfo_to_dict(config_local["HISTORIALES_POSTGRES_DSN"])
                            | {"dbname": nombre}
                        )
                    ),
                    jwt_secret="clave-local-de-pruebas-con-mas-de-32-caracteres",
                    mysql_host=None,
                    mysql_password=None,
                    mongodb_uri=None,
                    firestore_credentials=None,
                )
                yield conexion, settings
        finally:
            servidor.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(nombre))
            )


def cuentas(conexion):
    return conexion.execute(
        "SELECT id_profesional, correo, rol, establecimiento, password_hash, "
        "version_token, activo, debe_cambiar_contrasena FROM identidad.profesional ORDER BY correo"
    ).fetchall()


def test_migracion_arranque_y_cinco_logins_sin_duplicados(demo, capsys):
    conexion, settings = demo
    conexion.execute(MIGRACION_DEMO.read_text(encoding="utf-8"))
    originales = cuentas(conexion)
    assert len(originales) == 5
    assert all(not fila[7] for fila in originales)
    with TestClient(create_app(settings)) as client:
        for _, correo, rol, institucion, *_ in originales:
            respuesta = client.post(
                "/api/v1/auth/login", json={"correo": correo, "password": CONTRASENA_DEMO}
            )
            assert respuesta.status_code == 200, respuesta.text
            datos = respuesta.json()
            assert datos["usuario"]["rol"] == rol
            assert datos["usuario"]["institucion"] == institucion
            assert set(datos["usuario"]["permisos"]) == PERMISOS_POR_ROL[rol]
            headers = {"Authorization": "Bearer " + datos["access_token"]}
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
            assert client.get("/api/v1/pacientes?nombre=Ana", headers=headers).status_code == 403
    inicializar_cuentas_demo(settings)
    assert cuentas(conexion) == originales
    salida = capsys.readouterr().out
    for fila in originales:
        assert fila[1] in salida
    assert CONTRASENA_DEMO in salida
    assert "$argon2" not in salida


def test_conserva_administradores_personalizados_y_sus_permisos(demo, capsys):
    conexion, settings = demo
    cifrada = CifradorArgon2().cifrar("OtraContrasena2026!")
    for rol, institucion in [("superusuario", None), ("administrador", "hospital_general")]:
        identificador = uuid4()
        conexion.execute(
            "INSERT INTO identidad.profesional "
            "(id_profesional,correo,nombres,apellidos,password_hash,rol,establecimiento) "
            "VALUES (%s,%s,'Original','Conservado',%s,%s,%s)",
            (identificador, f"{rol}@existente.local", cifrada, rol, institucion),
        )
        for permiso in PERMISOS_POR_ROL[rol]:
            conexion.execute(
                "INSERT INTO identidad.profesional_permiso VALUES (%s,%s)",
                (identificador, permiso),
            )
    originales = cuentas(conexion)
    inicializar_cuentas_demo(settings)
    actuales = cuentas(conexion)
    assert len(actuales) == 5
    assert all(fila in actuales for fila in originales)
    salida = capsys.readouterr().out
    assert salida.count("contrasena existente conservada") == 2
    assert "superadmin@demo.local" not in salida


def test_no_restablece_contrasenas_estados_ni_sesiones(demo, capsys):
    conexion, settings = demo
    inicializar_cuentas_demo(settings)
    conexion.execute(
        "UPDATE identidad.profesional SET password_hash=%s, activo=FALSE, "
        "version_token=7, bloqueado_hasta='9999-12-31' WHERE establecimiento='hospital_general'",
        (CifradorArgon2().cifrar("CambioDelUsuario2026!"),),
    )
    anteriores = cuentas(conexion)
    capsys.readouterr()
    inicializar_cuentas_demo(settings)
    assert cuentas(conexion) == anteriores
    linea = next(
        texto for texto in capsys.readouterr().out.splitlines() if "Hospital General:" in texto
    )
    assert "INACTIVA" in linea
    assert "contrasena existente conservada" in linea
    assert CONTRASENA_DEMO not in linea


def test_arranques_simultaneos_son_idempotentes(demo):
    conexion, settings = demo
    with ThreadPoolExecutor(max_workers=3) as ejecutor:
        list(ejecutor.map(inicializar_cuentas_demo, [settings] * 3))
    assert len(cuentas(conexion)) == 5
    assert conexion.execute("SELECT count(*) FROM identidad.profesional_permiso").fetchone()[0] == 6
