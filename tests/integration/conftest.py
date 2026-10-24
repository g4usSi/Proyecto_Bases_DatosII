import os
import re
from uuid import uuid4

import pymysql
import pytest
from dotenv import dotenv_values

from app.core.config import PROJECT_ROOT


class ConfiguracionPrivada(dict):
    def __repr__(self):
        return "<configuracion local: secretos ocultos>"


def pytest_collection_modifyitems(items):
    if os.environ.get("HISTORIALES_TEST_INTEGRATION") == "1":
        return
    for item in items:
        if "integration" in str(item.path):
            item.add_marker(pytest.mark.skip(reason="Activar HISTORIALES_TEST_INTEGRATION=1"))


@pytest.fixture(scope="session")
def config_local():
    return ConfiguracionPrivada(dotenv_values(PROJECT_ROOT / ".env"))


def ejecutar_script(conn, ruta, nombre_bd):
    script = ruta.read_text(encoding="utf-8").replace("hospital_pediatrico", nombre_bd)
    delimitador = ";"
    buffer = []
    with conn.cursor() as cursor:
        for linea in script.splitlines():
            if linea.strip().startswith("DELIMITER "):
                delimitador = linea.strip().split()[1]
                continue
            if linea.strip().startswith("--") or not linea.strip():
                continue
            buffer.append(linea)
            if linea.rstrip().endswith(delimitador):
                cursor.execute("\n".join(buffer).rstrip()[: -len(delimitador)])
                buffer.clear()
    assert not buffer


@pytest.fixture(scope="module")
def mysql_pruebas(config_local):
    nombre = "prueba_historiales_" + uuid4().hex
    opciones = {
        "host": "127.0.0.1",
        "port": int(config_local.get("MYSQL_PORT", 3307)),
        "user": "root",
        "password": config_local["MYSQL_ROOT_PASSWORD"],
        "charset": "utf8mb4",
        "autocommit": True,
    }
    admin = pymysql.connect(**opciones)
    try:
        for archivo in (
            "001_hospital_pediatrico.sql",
            "002_integridad.sql",
            "004_escritura_api.sql",
        ):
            ejecutar_script(admin, PROJECT_ROOT / "database/mysql" / archivo, nombre)
        yield ConfiguracionPrivada({**opciones, "database": nombre, "autocommit": False})
    finally:
        # Solo puede eliminar la BD temporal creada por esta prueba.
        assert re.fullmatch(r"prueba_historiales_[0-9a-f]{32}", nombre)
        with admin.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{nombre}`")
        admin.close()


@pytest.fixture
def mysql_datos(mysql_pruebas):
    conn = pymysql.connect(**mysql_pruebas)
    with conn.cursor() as cursor:
        pacientes = []
        for _ in range(2):
            cursor.execute(
                "INSERT INTO paciente(numero_expediente,nombre,apellido,fecha_nacimiento,"
                "id_estado_fk) VALUES (%s,'Prueba','Sintetica','2020-01-01',1)",
                (uuid4().hex,),
            )
            pacientes.append(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO medico(nombre,apellido,colegiado) VALUES ('Profesional','Sintetico',%s)",
            (uuid4().hex,),
        )
        medico = cursor.lastrowid
        cursor.execute(
            "INSERT INTO consulta_medica(id_paciente,id_medico,motivo_consulta) "
            "VALUES (%s,%s,'Prueba')",
            (pacientes[0], medico),
        )
        consulta = cursor.lastrowid
    try:
        yield conn, pacientes, medico, consulta
    finally:
        conn.rollback()
        conn.close()
