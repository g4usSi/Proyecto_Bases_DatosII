"""Administracion de profesionales contra PostgreSQL real (y el vinculo en cada motor).

Crea cuentas sinteticas con correos @example.invalid y las borra al terminar. La bitacora
solo admite agregar; para limpiar se desactivan los triggers en la sesion administrativa
(session_replication_role = replica), algo que la cuenta de la API no puede hacer.
"""

import os
import threading
from uuid import uuid4

import psycopg
import pymysql
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pymongo import MongoClient

from app.core.config import Settings
from app.main import create_app

CLAVE_ADMIN = "Clave-admin-2026!"
CLAVE = "Clave-inicial-2026"


@pytest.fixture
def admin_pg(config_local):
    conexion = psycopg.connect(config_local["HISTORIALES_POSTGRES_ADMIN_DSN"], autocommit=True)
    yield conexion
    conexion.close()


@pytest.fixture
def entorno(config_local, admin_pg):
    marca = uuid4().hex[:10]
    creados: list[str] = []

    def crear_admin(institucion: str) -> str:
        identificador = uuid4()
        correo = f"admin-{marca}-{institucion}@example.invalid"
        admin_pg.execute(
            "INSERT INTO identidad.profesional "
            "(id_profesional, correo, nombres, apellidos, password_hash, establecimiento, rol) "
            "VALUES (%s, %s, 'Ada', 'Admin', %s, %s, 'administrador')",
            (identificador, correo, PasswordHash.recommended().hash(CLAVE_ADMIN), institucion),
        )
        admin_pg.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s, 'profesionales:administrar')",
            (identificador,),
        )
        creados.append(str(identificador))
        return correo

    departamento = admin_pg.execute(
        "INSERT INTO departamento (descripcion) VALUES (%s) RETURNING id_departamento",
        (f"Zz Area {marca}",),
    ).fetchone()[0]

    class Entorno:
        pass

    datos = Entorno()
    datos.marca = marca
    datos.crear_admin = crear_admin
    datos.departamento = departamento
    datos.correo = lambda nombre: f"{nombre}-{marca}@example.invalid"
    yield datos

    ids = [
        f[0]
        for f in admin_pg.execute(
            "SELECT id_profesional FROM identidad.profesional WHERE correo LIKE %s",
            (f"%{marca}%",),
        )
    ]
    with admin_pg.transaction():
        admin_pg.execute("SET LOCAL session_replication_role = replica")
        admin_pg.execute(
            "DELETE FROM identidad.bitacora_profesionales WHERE id_profesional = ANY(%s)", (ids,)
        )
        admin_pg.execute(
            "DELETE FROM personal_medico WHERE id_profesional_central = ANY(%s)", (ids,)
        )
        admin_pg.execute("DELETE FROM identidad.profesional WHERE id_profesional = ANY(%s)", (ids,))
        admin_pg.execute("DELETE FROM departamento WHERE id_departamento = %s", (departamento,))
    textos = [str(i) for i in ids]
    raiz = pymysql.connect(
        host="127.0.0.1",
        port=int(config_local["MYSQL_PORT"]),
        user="root",
        password=config_local["MYSQL_ROOT_PASSWORD"],
        database="hospital_pediatrico",
        autocommit=True,
    )
    with raiz.cursor() as cursor:
        for texto in textos:
            cursor.execute("DELETE FROM medico WHERE id_profesional_central = %s", (texto,))
    raiz.close()
    mongo = MongoClient(
        host="127.0.0.1",
        port=int(config_local["MONGO_PORT"]),
        username="historiales_admin",
        password=config_local["MONGO_ROOT_PASSWORD"],
        authSource="admin",
    )
    mongo.laboratorio_clinico.profesionales.delete_many({"id_profesional_central": {"$in": textos}})
    mongo.close()


def login(client, correo, clave):
    respuesta = client.post("/api/v1/auth/login", json={"correo": correo, "password": clave})
    return respuesta


def cabecera(respuesta) -> dict[str, str]:
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def test_flujo_completo_del_administrador_del_hospital(entorno, admin_pg):
    with TestClient(create_app(Settings())) as client:
        admin = cabecera(login(client, entorno.crear_admin("hospital_general"), CLAVE_ADMIN))
        departamentos = client.get("/api/v1/departamentos", headers=admin).json()
        assert {"id_departamento": entorno.departamento, "nombre": f"Zz Area {entorno.marca}"} in (
            departamentos
        )
        # El administrador no tiene acceso clinico.
        assert (
            client.get("/api/v1/pacientes", params={"nombre": "ana"}, headers=admin).status_code
            == 403
        )

        correo = entorno.correo("medico")
        alta = client.post(
            "/api/v1/profesionales",
            json={
                "correo": correo,
                "nombres": "Mario",
                "apellidos": "Zzprueba",
                "rol": "medico",
                "id_departamento": entorno.departamento,
                "permisos": ["historiales:leer"],
                "contrasena_inicial": CLAVE,
            },
            headers=admin,
        )
        assert alta.status_code == 201, alta.text
        ficha = alta.json()["profesional"]
        identificador = ficha["id_profesional"]
        assert alta.json()["vinculado"] is True
        assert ficha["departamento"] == f"Zz Area {entorno.marca}"
        assert ficha["permisos"] == ["historiales:leer", "pacientes:leer"]
        assert ficha["estado"] == "activa" and ficha["debe_cambiar_contrasena"] is True
        perfil = admin_pg.execute(
            "SELECT rol, estado FROM personal_medico WHERE id_profesional_central = %s",
            (identificador,),
        ).fetchone()
        assert perfil == ("Medico", "Activo")
        bitacora = admin_pg.execute(
            "SELECT accion, detalle::text FROM identidad.bitacora_profesionales "
            "WHERE id_profesional = %s",
            (identificador,),
        ).fetchall()
        assert [a for a, _ in bitacora] == ["alta"]
        assert CLAVE not in bitacora[0][1] and "argon" not in bitacora[0][1]

        duplicado = client.post(
            "/api/v1/profesionales",
            json={"correo": correo.upper(), "nombres": "X", "apellidos": "Y", "rol": "medico"},
            headers=admin,
        )
        assert duplicado.status_code == 409

        # La persona entra, ve que debe cambiar su contrasena y la cambia.
        medico = cabecera(login(client, correo, CLAVE))
        me = client.get("/api/v1/auth/me", headers=medico).json()
        assert me["debe_cambiar_contrasena"] is True and me["rol"] == "medico"
        cambio = client.post(
            "/api/v1/auth/cambiar-contrasena",
            json={"contrasena_actual": CLAVE, "contrasena_nueva": "Mi-clave-propia-77"},
            headers=medico,
        )
        assert cambio.status_code == 200
        assert client.get("/api/v1/auth/me", headers=medico).status_code == 401  # sesion vieja
        medico = cabecera(cambio)
        assert (
            client.get("/api/v1/auth/me", headers=medico).json()["debe_cambiar_contrasena"] is False
        )
        assert login(client, correo, CLAVE).status_code == 401

        # Los permisos cambian en la siguiente peticion, sin volver a entrar.
        ruta = f"/api/v1/profesionales/{identificador}"
        assert (
            client.patch(ruta, json={"permisos": ["citas:leer"]}, headers=admin).status_code == 200
        )
        assert client.get("/api/v1/auth/me", headers=medico).json()["permisos"] == [
            "citas:leer",
            "pacientes:leer",
        ]
        agenda = client.get("/api/v1/citas/profesionales", headers=medico).json()
        assert identificador in [p["id_profesional"] for p in agenda]

        # Bloquear corta el acceso de inmediato; activar lo devuelve.
        bloqueo = client.patch(ruta, json={"estado": "bloqueada"}, headers=admin)
        assert bloqueo.json()["profesional"]["estado"] == "bloqueada"
        assert client.get("/api/v1/auth/me", headers=medico).status_code == 401
        assert login(client, correo, "Mi-clave-propia-77").status_code == 401
        filtrados = client.get(
            "/api/v1/profesionales", params={"estado": "bloqueada"}, headers=admin
        ).json()
        assert [p["id_profesional"] for p in filtrados] == [identificador]
        client.patch(ruta, json={"estado": "activa"}, headers=admin)
        medico = cabecera(login(client, correo, "Mi-clave-propia-77"))

        # Restablecer: la contrasena anterior deja de servir; la nueva se muestra una vez.
        restablecida = client.post(f"{ruta}/restablecer-contrasena", headers=admin)
        assert restablecida.headers["cache-control"] == "no-store"
        temporal = restablecida.json()["contrasena_temporal"]
        assert client.get("/api/v1/auth/me", headers=medico).status_code == 401
        assert login(client, correo, "Mi-clave-propia-77").status_code == 401
        assert (
            client.get("/api/v1/auth/me", headers=cabecera(login(client, correo, temporal))).json()[
                "debe_cambiar_contrasena"
            ]
            is True
        )

        # Inactivar tambien desactiva el perfil local del hospital.
        inactiva = client.patch(ruta, json={"estado": "inactiva"}, headers=admin)
        assert inactiva.json()["vinculado"] is True
        assert admin_pg.execute(
            "SELECT estado FROM personal_medico WHERE id_profesional_central = %s",
            (identificador,),
        ).fetchone() == ("Inactivo",)
        acciones = [
            f[0]
            for f in admin_pg.execute(
                "SELECT accion FROM identidad.bitacora_profesionales WHERE id_profesional = %s "
                "ORDER BY id_evento",
                (identificador,),
            )
        ]
        assert acciones == [
            "alta",
            "cambiar_contrasena",
            "cambio",
            "cambio",
            "cambio",
            "restablecer_contrasena",
            "cambio",
        ]
        # El administrador no aparece en la lista ni puede tocarse a si mismo por la API.
        assert all(
            p["rol"] != "administrador"
            for p in client.get("/api/v1/profesionales", headers=admin).json()
        )


def test_cada_administrador_solo_ve_su_institucion_y_vincula_en_su_motor(entorno, config_local):
    with TestClient(create_app(Settings())) as client:
        hospital = cabecera(login(client, entorno.crear_admin("hospital_general"), CLAVE_ADMIN))
        lab = cabecera(login(client, entorno.crear_admin("laboratorio_clinico"), CLAVE_ADMIN))
        pediatria = cabecera(login(client, entorno.crear_admin("centro_pediatrico"), CLAVE_ADMIN))

        del_hospital = client.post(
            "/api/v1/profesionales",
            json={
                "correo": entorno.correo("enf"),
                "nombres": "Eva",
                "apellidos": "Zz",
                "rol": "enfermeria",
            },
            headers=hospital,
        ).json()
        id_hospital = del_hospital["profesional"]["id_profesional"]
        assert del_hospital["contrasena_temporal"]  # no se envio: se genero una
        assert client.get(f"/api/v1/profesionales/{id_hospital}", headers=lab).status_code == 404
        assert (
            client.patch(
                f"/api/v1/profesionales/{id_hospital}", json={"estado": "inactiva"}, headers=lab
            ).status_code
            == 404
        )
        assert client.get("/api/v1/departamentos", headers=lab).status_code == 501

        laboratorista = client.post(
            "/api/v1/profesionales",
            json={
                "correo": entorno.correo("lab"),
                "nombres": "Lia",
                "apellidos": "Zz",
                "rol": "laboratorista",
            },
            headers=lab,
        ).json()
        assert laboratorista["vinculado"] is True
        assert laboratorista["profesional"]["permisos"] == [
            "laboratorio:resultados",
            "laboratorio:validar",
            "pacientes:leer",
        ]
        mongo = MongoClient(config_local["HISTORIALES_MONGODB_URI"])
        documento = mongo.laboratorio_clinico.profesionales.find_one(
            {"id_profesional_central": laboratorista["profesional"]["id_profesional"]}
        )
        mongo.close()
        assert documento["rol"] == "laboratorista" and documento["activo"] is True

        pediatra = client.post(
            "/api/v1/profesionales",
            json={
                "correo": entorno.correo("ped"),
                "nombres": "Pia",
                "apellidos": "Zz",
                "rol": "medico",
                "permisos": ["consultas:registrar", "historiales:leer"],
            },
            headers=pediatria,
        ).json()
        assert pediatra["vinculado"] is True
        id_pediatra = pediatra["profesional"]["id_profesional"]
        client.patch(
            f"/api/v1/profesionales/{id_pediatra}", json={"estado": "inactiva"}, headers=pediatria
        )
        raiz = pymysql.connect(
            host="127.0.0.1",
            port=int(config_local["MYSQL_PORT"]),
            user="root",
            password=config_local["MYSQL_ROOT_PASSWORD"],
            database="hospital_pediatrico",
        )
        with raiz.cursor() as cursor:
            cursor.execute(
                "SELECT colegiado, activo FROM medico WHERE id_profesional_central = %s",
                (id_pediatra,),
            )
            assert cursor.fetchone() == (f"PEND-{id_pediatra}", 0)
        raiz.close()
        # Un rol o permiso de otra institucion se rechaza.
        assert (
            client.post(
                "/api/v1/profesionales",
                json={
                    "correo": entorno.correo("x"),
                    "nombres": "X",
                    "apellidos": "Y",
                    "rol": "laboratorista",
                },
                headers=pediatria,
            ).status_code
            == 422
        )


def test_dos_altas_simultaneas_con_el_mismo_correo(entorno):
    with TestClient(create_app(Settings())) as client:
        admin = cabecera(login(client, entorno.crear_admin("hospital_general"), CLAVE_ADMIN))
        correo = entorno.correo("doble")
        resultados = []
        barrera = threading.Barrier(2)

        def alta():
            barrera.wait(timeout=10)
            resultados.append(
                client.post(
                    "/api/v1/profesionales",
                    json={"correo": correo, "nombres": "D", "apellidos": "Zz", "rol": "medico"},
                    headers=admin,
                ).status_code
            )

        hilos = [threading.Thread(target=alta) for _ in range(2)]
        [h.start() for h in hilos]
        [h.join(timeout=30) for h in hilos]
    assert sorted(resultados) == [201, 409]


def test_la_base_impone_las_reglas_del_administrador(entorno, admin_pg, config_local):
    correo = entorno.crear_admin("hospital_general")
    id_admin = admin_pg.execute(
        "SELECT id_profesional FROM identidad.profesional WHERE correo = %s", (correo,)
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        admin_pg.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s, 'historiales:leer')", (id_admin,)
        )
    id_medico = uuid4()
    admin_pg.execute(
        "INSERT INTO identidad.profesional (id_profesional, correo, nombres, apellidos, "
        "password_hash, establecimiento, rol) VALUES (%s, %s, 'M', 'Zz', %s, "
        "'laboratorio_clinico', 'medico')",
        (id_medico, entorno.correo("regla"), PasswordHash.recommended().hash(CLAVE)),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        admin_pg.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s, 'profesionales:administrar')",
            (id_medico,),
        )
    with pytest.raises(psycopg.errors.CheckViolation):  # area fuera del hospital
        admin_pg.execute(
            "UPDATE identidad.profesional SET id_departamento = %s WHERE id_profesional = %s",
            (entorno.departamento, id_medico),
        )
    admin_pg.execute(
        "INSERT INTO identidad.bitacora_profesionales (id_actor, id_profesional, "
        "establecimiento, accion) VALUES (%s, %s, 'laboratorio_clinico', 'cambio')",
        (id_admin, id_medico),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        admin_pg.execute("UPDATE identidad.bitacora_profesionales SET accion = 'alta'")
    app = psycopg.connect(config_local["HISTORIALES_POSTGRES_DSN"], autocommit=True)
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute("DELETE FROM identidad.bitacora_profesionales")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute("UPDATE identidad.profesional SET rol = 'administrador'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute("DELETE FROM identidad.profesional")
    finally:
        app.close()


@pytest.mark.skipif(
    not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="Requiere el emulador de Firestore."
)
def test_vinculo_del_perfil_en_firestore():
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    from app.domain.profesional import ProfesionalLocal
    from app.infrastructure.persistence.firestore.unidad import UnidadTrabajoFirestore

    cliente = firestore.Client(project="prueba-local", credentials=AnonymousCredentials())
    identificador = str(uuid4())
    try:
        with UnidadTrabajoFirestore(cliente) as unidad:
            unidad.profesionales.sincronizar(
                ProfesionalLocal(identificador, "Odo", "Zz", "odontologo", True)
            )
            assert unidad.profesionales.obtener(identificador) is None  # aun en el batch
            unidad.commit()
        with UnidadTrabajoFirestore(cliente) as unidad:
            perfil = unidad.profesionales.obtener(identificador)
        assert perfil == ProfesionalLocal(identificador, "Odo", "Zz", "odontologo", True)
    finally:
        cliente.collection("profesionales").document(identificador).delete()
        cliente.close()
