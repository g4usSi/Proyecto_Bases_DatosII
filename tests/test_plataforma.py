from dataclasses import replace

import jwt
import pytest

from app.domain.administracion import EstadoCuenta, ResumenPersonal
from app.domain.errores import TokenInvalido
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from tests.test_identidad import PASSWORD, SECRETO
from tests.test_identidad import autenticador as autenticador
from tests.test_profesionales import ADMIN, AUTH, alta, preparar

SUPER = UsuarioAutenticado(
    "plataforma", None, frozenset({"plataforma:administrar", "pagos:ver"}), rol="superusuario"
)


@pytest.mark.parametrize("institucion", list(Institucion))
def test_superusuario_crea_personal_y_administrador(settings, institucion):
    client, _, _, _ = preparar(settings, {"admin": SUPER})
    with client:
        rol = "odontologo" if institucion == Institucion.CLINICA_ODONTOLOGICA else "medico"
        personal = alta(client, establecimiento=institucion.value, rol=rol)
        admin = alta(
            client,
            establecimiento=institucion.value,
            rol="administrador",
            correo="admin2@example.invalid",
        )
        duplicado = alta(
            client,
            establecimiento=institucion.value,
            rol="administrador",
            correo="admin3@example.invalid",
        )
        lista = client.get("/api/v1/profesionales", headers=AUTH)
    assert personal.status_code == admin.status_code == 201
    assert admin.json()["profesional"]["permisos"] == ["profesionales:administrar"]
    assert duplicado.status_code == 409
    assert len(lista.json()) == 2


def test_superusuario_baja_definitiva_y_correo_reservado(settings):
    client, directorio, _, _ = preparar(settings, {"admin": SUPER, "entidad": ADMIN})
    with client:
        creado = alta(client, establecimiento="hospital_general").json()["profesional"]
        ruta = "/api/v1/profesionales/" + creado["id_profesional"]
        assert client.delete(ruta, headers={"Authorization": "Bearer entidad"}).status_code == 403
        assert client.delete(ruta, headers=AUTH).status_code == 204
        assert client.get(ruta, headers=AUTH).status_code == 404
        assert client.delete(ruta, headers=AUTH).status_code == 409
        assert client.patch(ruta, json={"estado": "activa"}, headers=AUTH).status_code == 409
        assert client.patch(ruta, json={"estado": "eliminada"}, headers=AUTH).status_code == 422
        assert alta(client, establecimiento="hospital_general").status_code == 409
        assert client.get("/api/v1/profesionales", headers=AUTH).json() == []
    assert directorio.fichas[creado["id_profesional"]].estado == EstadoCuenta.ELIMINADA


def test_alcance_y_roles_de_administracion(settings):
    client, _, _, _ = preparar(settings, {"admin": ADMIN, "super": SUPER})
    with client:
        assert alta(client, establecimiento="hospital_general").status_code == 422
        assert alta(client, rol="administrador").status_code == 403
        assert (
            client.get(
                "/api/v1/profesionales?establecimiento=laboratorio_clinico", headers=AUTH
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/v1/profesionales/bitacora?establecimiento=laboratorio_clinico", headers=AUTH
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/v1/profesionales/resumen?establecimiento=laboratorio_clinico", headers=AUTH
            ).status_code
            == 403
        )
        assert client.get("/api/v1/plataforma/resumen", headers=AUTH).status_code == 403
        assert (
            client.post(
                "/api/v1/profesionales",
                json={"correo": "a@b.com", "nombres": "A", "apellidos": "B", "rol": "medico"},
                headers={"Authorization": "Bearer super"},
            ).status_code
            == 422
        )


def test_plataforma_no_abre_motores_clinicos_ni_escribe_pagos(settings):
    contaminado = replace(
        SUPER,
        permisos=SUPER.permisos
        | {
            "pacientes:leer",
            "historiales:leer",
            "citas:leer",
            "laboratorio:resultados",
            "pagos:registrar",
        },
    )
    client, _, _, _ = preparar(settings, {"admin": contaminado})
    with client:
        for ruta in (
            "/pacientes?nombre=Ana",
            "/citas",
            "/laboratorio/ordenes",
            "/pacientes/1/odontograma",
        ):
            assert client.get("/api/v1" + ruta, headers=AUTH).status_code == 403
        assert (
            client.post(
                "/api/v1/pacientes/1/cobros", json={"id_atencion": "1"}, headers=AUTH
            ).status_code
            == 403
        )
        for entidad in (None, "laboratorio_clinico", "clinica_odontologica"):
            parametros = {"establecimiento": entidad} if entidad else {}
            assert client.get("/api/v1/cobros", params=parametros, headers=AUTH).status_code == 422


def test_resumen_parcial_conteos_y_sin_pacientes(settings):
    client, directorio, unidad, _ = preparar(settings, {"admin": SUPER})
    directorio.resumen = lambda i: ResumenPersonal(
        {"activa": 2, "inactiva": 1}, 0, 1, {"medico": 2}, None, [], "Ada Admin"
    )
    unidad.resumen_operativo = lambda d, h: {"pacientes_registrados": 12, "citas_hoy": 3}
    with client:
        respuesta = client.get("/api/v1/plataforma/resumen", headers=AUTH)
    assert respuesta.status_code == 200
    assert respuesta.json()["hospital_general"]["pacientes_registrados"] == 12
    assert respuesta.json()["hospital_general"]["personal_sin_acceso"] == 1
    assert respuesta.json()["laboratorio_clinico"] is None
    assert "id_paciente" not in respuesta.text and "password" not in respuesta.text


def test_token_plataforma_admite_null_pero_exige_claim_inst(autenticador):
    cuenta = replace(
        autenticador.directorio.cuenta,
        institucion=None,
        rol="superusuario",
        permisos=SUPER.permisos,
    )
    autenticador.directorio.cuenta = cuenta
    token = autenticador.iniciar_sesion(cuenta.correo, PASSWORD).access_token
    assert autenticador.verificar_token(token).es_plataforma
    payload = jwt.decode(
        token, SECRETO, algorithms=["HS256"], audience="api-pruebas", issuer="pruebas"
    )
    assert payload.pop("inst") is None
    with pytest.raises(TokenInvalido):
        autenticador.verificar_token(jwt.encode(payload, SECRETO, algorithm="HS256"))
