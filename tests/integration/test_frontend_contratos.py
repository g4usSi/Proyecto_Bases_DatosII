"""Brechas del mockup: datos reales con la cuenta limitada y limpieza sintetica."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from app.core.config import Settings
from app.main import create_app
from tests.integration.test_administracion import admin_pg as admin_pg
from tests.integration.test_administracion import entorno as entorno
from tests.integration.test_hospital import admin as admin

CLAVE = "Clave-plataforma-2026!"


@pytest.fixture
def plataforma(entorno, admin_pg):
    identificador = uuid4()
    correo = entorno.correo("superusuario")
    admin_pg.execute(
        "INSERT INTO identidad.profesional "
        "(id_profesional,correo,nombres,apellidos,password_hash,establecimiento,rol) "
        "VALUES (%s,%s,'Super','Prueba',%s,NULL,'superusuario')",
        (identificador, correo, PasswordHash.recommended().hash(CLAVE)),
    )
    for permiso in ("plataforma:administrar", "pagos:ver"):
        admin_pg.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s,%s)", (identificador, permiso)
        )
    with TestClient(create_app(Settings())) as client:
        login = client.post("/api/v1/auth/login", json={"correo": correo, "password": CLAVE})
        assert login.status_code == 200, login.text
        assert login.json()["usuario"]["institucion"] is None
        yield (
            client,
            {"Authorization": "Bearer " + login.json()["access_token"]},
            str(identificador),
        )


def crear(client, cabecera, entorno, institucion, rol="medico", nombre="personal"):
    respuesta = client.post(
        "/api/v1/profesionales",
        json={
            "establecimiento": institucion,
            "correo": entorno.correo(nombre),
            "nombres": "Persona",
            "apellidos": "Sintetica",
            "rol": rol,
            "contrasena_inicial": "Clave-inicial-2026",
        },
        headers=cabecera,
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["profesional"]


def test_superusuario_administra_y_elimina_sin_reactivar(plataforma, entorno, admin_pg):
    client, h, super_id = plataforma
    admin = crear(client, h, entorno, "hospital_general", "administrador", "admin-hospital")
    medico = crear(client, h, entorno, "hospital_general")
    laboratorio = crear(client, h, entorno, "laboratorio_clinico", "laboratorista", "lab")
    assert laboratorio["permisos"] == [
        "laboratorio:resultados",
        "laboratorio:validar",
        "pacientes:leer",
    ]
    duplicado = client.post(
        "/api/v1/profesionales",
        json={
            "establecimiento": "hospital_general",
            "correo": entorno.correo("otro-admin"),
            "nombres": "A",
            "apellidos": "B",
            "rol": "administrador",
        },
        headers=h,
    )
    assert duplicado.status_code == 409
    assert client.delete("/api/v1/profesionales/" + super_id, headers=h).status_code == 404
    login = client.post(
        "/api/v1/auth/login", json={"correo": medico["correo"], "password": "Clave-inicial-2026"}
    )
    antiguo = {"Authorization": "Bearer " + login.json()["access_token"]}
    ruta = "/api/v1/profesionales/" + medico["id_profesional"]
    assert client.delete(ruta, headers=h).status_code == 204
    assert client.get("/api/v1/auth/me", headers=antiguo).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"correo": medico["correo"], "password": "Clave-inicial-2026"},
        ).status_code
        == 401
    )
    assert client.patch(ruta, json={"estado": "activa"}, headers=h).status_code == 409
    assert client.delete(ruta, headers=h).status_code == 409
    assert client.get(ruta, headers=h).status_code == 404
    assert (
        client.get("/api/v1/profesionales/" + admin["id_profesional"], headers=h).status_code == 200
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        admin_pg.execute(
            "UPDATE identidad.profesional SET activo=TRUE, eliminado_en=NULL "
            "WHERE id_profesional=%s",
            (medico["id_profesional"],),
        )
    with pytest.raises(psycopg.errors.UniqueViolation):
        admin_pg.execute(
            "INSERT INTO identidad.profesional (id_profesional,correo,nombres,apellidos,"
            "password_hash,establecimiento,rol) VALUES (%s,%s,'X','Y',%s,NULL,'superusuario')",
            (uuid4(), entorno.correo("otro-super"), PasswordHash.recommended().hash(CLAVE)),
        )


def test_bitacora_resumen_aislamiento_y_pagos_de_lectura(plataforma, entorno, admin_pg):
    client, h, _ = plataforma
    admin = crear(client, h, entorno, "hospital_general", "administrador", "admin-hospital")
    medico = crear(client, h, entorno, "hospital_general")
    crear(client, h, entorno, "laboratorio_clinico", "laboratorista", "lab")
    admin_pg.execute(
        "UPDATE identidad.profesional SET bloqueado_hasta=now()+interval '10 minutes' "
        "WHERE id_profesional=%s",
        (medico["id_profesional"],),
    )
    resumen = client.get(
        "/api/v1/profesionales/resumen?establecimiento=hospital_general", headers=h
    )
    assert resumen.status_code == 200, resumen.text
    assert resumen.json()["bloqueadas_por_intentos"] == 1
    assert resumen.json()["por_estado"]["bloqueada"] == 1
    assert resumen.json()["activos_por_departamento"] == {}
    evento = client.get("/api/v1/profesionales/bitacora?limite=1", headers=h).json()[0]
    siguiente = client.get(
        "/api/v1/profesionales/bitacora", params={"antes_de": evento["id_evento"]}, headers=h
    )
    assert siguiente.status_code == 200 and all(
        e["id_evento"] < evento["id_evento"] for e in siguiente.json()
    )
    assert "password_hash" not in siguiente.text and "Clave-" not in siguiente.text
    login = client.post(
        "/api/v1/auth/login", json={"correo": admin["correo"], "password": "Clave-inicial-2026"}
    )
    ha = {"Authorization": "Bearer " + login.json()["access_token"]}
    propias = client.get("/api/v1/profesionales/bitacora", headers=ha)
    assert propias.status_code == 200 and all(
        e["institucion"] == "hospital_general" for e in propias.json()
    )
    assert (
        client.get(
            "/api/v1/profesionales/bitacora?establecimiento=laboratorio_clinico", headers=ha
        ).status_code
        == 403
    )
    assert (
        client.delete("/api/v1/profesionales/" + medico["id_profesional"], headers=ha).status_code
        == 403
    )
    for ruta in ("/pacientes?nombre=Ana", "/citas", "/laboratorio/ordenes"):
        assert client.get("/api/v1" + ruta, headers=h).status_code == 403
    assert (
        client.get("/api/v1/cobros?establecimiento=hospital_general", headers=h).status_code == 200
    )
    assert (
        client.get("/api/v1/cobros?establecimiento=centro_pediatrico", headers=h).status_code == 200
    )
    assert (
        client.get("/api/v1/cobros?establecimiento=laboratorio_clinico", headers=h).status_code
        == 422
    )
    assert (
        client.post("/api/v1/pacientes/1/cobros", json={"id_atencion": "1"}, headers=h).status_code
        == 403
    )
    tablero = client.get("/api/v1/plataforma/resumen", headers=h)
    cobros_pediatricos = client.get(
        "/api/v1/cobros/resumen?establecimiento=centro_pediatrico", headers=h
    )
    assert cobros_pediatricos.status_code == 200, cobros_pediatricos.text
    assert cobros_pediatricos.json()["pagos_anulados"] == 0
    assert tablero.status_code == 200, tablero.text
    assert tablero.json()["hospital_general"] is not None
    assert tablero.json()["laboratorio_clinico"] is not None
    assert "id_paciente" not in tablero.text
    antes = datetime.now(UTC) - timedelta(days=1)
    despues = datetime.now(UTC) + timedelta(days=1)
    assert (
        client.get(
            "/api/v1/profesionales/bitacora",
            params={"desde": despues.isoformat(), "hasta": antes.isoformat()},
            headers=h,
        ).status_code
        == 422
    )


def test_superusuario_cambia_su_contrasena_con_bitacora(plataforma):
    client, h, _ = plataforma
    cambio = client.post(
        "/api/v1/auth/cambiar-contrasena",
        json={"contrasena_actual": CLAVE, "contrasena_nueva": "Clave-renovada-2030"},
        headers=h,
    )
    assert cambio.status_code == 200, cambio.text
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
    nuevo = {"Authorization": "Bearer " + cambio.json()["access_token"]}
    eventos = client.get(
        "/api/v1/profesionales/bitacora?accion=cambiar_contrasena", headers=nuevo
    ).json()
    assert eventos[0]["institucion"] is None


def test_migraciones_nuevas_son_idempotentes(admin):
    from app.core.config import PROJECT_ROOT

    for archivo in ("015_administracion_dos_niveles.sql",):
        for _ in range(2):
            admin.execute(
                (PROJECT_ROOT / "database/postgresql" / archivo).read_text(encoding="utf-8")
            )
