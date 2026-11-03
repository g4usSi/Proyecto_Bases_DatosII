from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pymysql
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pymongo import MongoClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.parametrize(
    "institucion", ["hospital_general", "centro_pediatrico", "laboratorio_clinico"]
)
def test_login_postgres_y_lectura_del_motor_autorizado(config_local, institucion):
    profesional = uuid4()
    correo = f"prueba-{profesional}@example.invalid"
    password = "Contrasena sintetica de prueba"
    pg = psycopg.connect(config_local["HISTORIALES_POSTGRES_ADMIN_DSN"], autocommit=True)
    mysql = pymysql.connect(
        host="127.0.0.1",
        port=int(config_local["MYSQL_PORT"]),
        user="root",
        password=config_local["MYSQL_ROOT_PASSWORD"],
        database=config_local.get("HISTORIALES_MYSQL_DATABASE", "hospital_pediatrico"),
        autocommit=True,
    )
    mongo = MongoClient(
        host="127.0.0.1",
        port=int(config_local["MONGO_PORT"]),
        username="historiales_admin",
        password=config_local["MONGO_ROOT_PASSWORD"],
        authSource="admin",
    )
    id_paciente = None
    try:
        pg.execute(
            "INSERT INTO identidad.profesional "
            "(id_profesional,correo,nombres,apellidos,password_hash,establecimiento,rol) "
            "VALUES (%s,%s,'Prueba','Profesional',%s,%s,'medico')",
            (profesional, correo, PasswordHash.recommended().hash(password), institucion),
        )
        pg.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s,'pacientes:leer')", (profesional,)
        )
        if institucion == "hospital_general":
            id_paciente = pg.execute(
                "INSERT INTO paciente(nombres,apellidos) "
                "VALUES ('Paciente PG sintetico','Prueba') RETURNING id_paciente"
            ).fetchone()[0]
        elif institucion == "centro_pediatrico":
            with mysql.cursor() as c:
                c.execute(
                    "INSERT INTO paciente(numero_expediente,nombre,apellido,"
                    "fecha_nacimiento,id_estado_fk) "
                    "VALUES (%s,'Paciente MySQL sintetico','Prueba','2020-01-01',1)",
                    (uuid4().hex,),
                )
                id_paciente = c.lastrowid
        else:
            id_paciente = ObjectId()
            mongo.laboratorio_clinico.pacientes.insert_one(
                {
                    "_id": id_paciente,
                    "numero_expediente": uuid4().hex,
                    "nombres": "Paciente Mongo sintetico",
                    "apellidos": "Prueba",
                    "estado": "Activo",
                    "creado_en": datetime.now(UTC),
                    "actualizado_en": datetime.now(UTC),
                }
            )
        with TestClient(create_app(Settings())) as client:
            login = client.post("/api/v1/auth/login", json={"correo": correo, "password": password})
            assert login.status_code == 200
            assert login.json()["usuario"]["institucion"] == institucion
            headers = {
                "Authorization": f"Bearer {login.json()['access_token']}",
                "X-Institucion": "clinica_odontologica",
            }
            lectura = client.get(f"/api/v1/pacientes/{id_paciente}", headers=headers)
            assert lectura.status_code == 200
            assert "sintetico" in lectura.json()["nombres"]
            assert lectura.json()["id_paciente"] == str(id_paciente)
            # La desactivacion administrativa tiene efecto sobre un token ya emitido.
            pg.execute(
                "UPDATE identidad.profesional SET activo=false WHERE id_profesional=%s",
                (profesional,),
            )
            assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    finally:
        if id_paciente is not None:
            if institucion == "hospital_general":
                pg.execute("DELETE FROM paciente WHERE id_paciente=%s", (id_paciente,))
            elif institucion == "centro_pediatrico":
                with mysql.cursor() as c:
                    c.execute("DELETE FROM paciente WHERE id_paciente=%s", (id_paciente,))
            else:
                mongo.laboratorio_clinico.pacientes.delete_one({"_id": id_paciente})
        pg.execute("DELETE FROM identidad.profesional WHERE id_profesional=%s", (profesional,))
        pg.close()
        mysql.close()
        mongo.close()
