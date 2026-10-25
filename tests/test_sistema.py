"""Auditoria de accesos y verificacion de disponibilidad (sin motores reales)."""

import logging

from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.paciente import Paciente
from app.main import create_app
from tests.doubles import AutenticadorDoble, UnidadTrabajoDoble

AUTH = {"Authorization": "Bearer valido"}


def cliente(settings: Settings, permisos: frozenset[str]) -> TestClient:
    usuario = UsuarioAutenticado("prof-77", Institucion.CLINICA_ODONTOLOGICA, permisos)
    unidad = UnidadTrabajoDoble({"5": Paciente("5", "Ana", "Lopez")})
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"valido": usuario}),
        unidades_trabajo={Institucion.CLINICA_ODONTOLOGICA: lambda: unidad},
    )
    return TestClient(create_app(settings, contenedor))


def test_cada_acceso_queda_en_la_bitacora_sin_datos_clinicos(settings, caplog) -> None:
    caplog.set_level(logging.INFO, logger="auditoria")
    with cliente(settings, frozenset({"pacientes:leer"})) as client:
        assert client.get("/api/v1/pacientes/5", headers=AUTH).status_code == 200
    registros = [r.getMessage() for r in caplog.records if r.name == "auditoria"]
    assert len(registros) == 1
    linea = registros[0]
    assert "evento=acceso" in linea and "usuario=prof-77" in linea
    assert "institucion=clinica_odontologica" in linea and "paciente=5" in linea
    assert "permiso=pacientes:leer" in linea and "ruta=/pacientes/{id_paciente}" in linea
    assert "Ana" not in linea and "Lopez" not in linea  # nunca datos del paciente


def test_un_acceso_denegado_queda_como_advertencia(settings, caplog) -> None:
    caplog.set_level(logging.INFO, logger="auditoria")
    with cliente(settings, frozenset({"pacientes:leer"})) as client:
        respuesta = client.get("/api/v1/pacientes/5/historial", headers=AUTH)
    assert respuesta.status_code == 403
    denegados = [r for r in caplog.records if r.name == "auditoria"]
    assert [r.levelno for r in denegados] == [logging.WARNING]
    assert "evento=acceso_denegado" in denegados[0].getMessage()
    assert "permiso=historiales:leer" in denegados[0].getMessage()


def test_sin_token_no_hay_registro_de_auditoria(settings, caplog) -> None:
    caplog.set_level(logging.INFO, logger="auditoria")
    with cliente(settings, frozenset({"pacientes:leer"})) as client:
        assert client.get("/api/v1/pacientes/5").status_code == 401
    assert not [r for r in caplog.records if r.name == "auditoria"]


def test_ready_distingue_ok_caido_y_no_configurado(settings) -> None:
    def caida() -> None:
        raise RuntimeError("secreto: password=abc")

    contenedor = Contenedor(
        verificaciones={
            Institucion.HOSPITAL_GENERAL: lambda: None,
            Institucion.CENTRO_PEDIATRICO: caida,
        }
    )
    with TestClient(create_app(settings, contenedor)) as client:
        respuesta = client.get("/health/ready")
    assert respuesta.status_code == 503
    datos = respuesta.json()
    assert datos["status"] == "degradado"
    assert datos["instituciones"] == {
        "hospital_general": "ok",
        "centro_pediatrico": "no_disponible",
        "laboratorio_clinico": "no_configurada",
        "clinica_odontologica": "no_configurada",
    }
    assert "secreto" not in respuesta.text  # el detalle del error no sale en la respuesta


def test_ready_ok_si_lo_configurado_responde(settings) -> None:
    contenedor = Contenedor(verificaciones={Institucion.HOSPITAL_GENERAL: lambda: None})
    with TestClient(create_app(settings, contenedor)) as client:
        respuesta = client.get("/health/ready")
    assert respuesta.status_code == 200 and respuesta.json()["status"] == "ok"
