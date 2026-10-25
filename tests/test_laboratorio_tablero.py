"""Rutas nuevas del laboratorio con dobles: permisos y 501 fuera del Laboratorio Clinico."""

from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.main import create_app
from tests.doubles import AutenticadorDoble, UnidadTrabajoDoble


def cliente(settings: Settings, permisos: frozenset[str]) -> TestClient:
    usuario = UsuarioAutenticado("u1", Institucion.HOSPITAL_GENERAL, permisos)
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"t": usuario}),
        unidades_trabajo={Institucion.HOSPITAL_GENERAL: lambda: UnidadTrabajoDoble({})},
    )
    return TestClient(create_app(settings, contenedor))


def test_tablero_y_versiones_solo_en_el_laboratorio(settings: Settings) -> None:
    h = {"Authorization": "Bearer t"}
    with cliente(settings, frozenset({"historiales:leer"})) as client:
        tablero = client.get("/api/v1/laboratorio/ordenes", headers=h)
        versiones = client.get("/api/v1/laboratorio/pruebas/HGB/versiones", headers=h)
        cursor_sin_zona = client.get(
            "/api/v1/laboratorio/ordenes", params={"antes_de": "2026-01-01T10:00:00"}, headers=h
        )
    assert tablero.status_code == 501 and "Laboratorio Clinico" in tablero.text
    assert versiones.status_code == 501
    assert cursor_sin_zona.status_code == 422


def test_tablero_exige_permiso_de_lectura_o_resultados(settings: Settings) -> None:
    with cliente(settings, frozenset({"pacientes:leer"})) as client:
        respuesta = client.get("/api/v1/laboratorio/ordenes", headers={"Authorization": "Bearer t"})
    assert respuesta.status_code == 403
