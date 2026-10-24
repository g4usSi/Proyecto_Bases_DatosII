"""Contrato comun de las operaciones del curso, probado con dobles (sin motores)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.paciente import Paciente
from app.infrastructure.persistence.sql import UnidadTrabajoSQL
from app.main import create_app
from tests.doubles import AutenticadorDoble, HistorialDoble, UnidadTrabajoDoble

TODOS = frozenset(
    {
        "pacientes:leer",
        "pacientes:registrar",
        "historiales:leer",
        "consultas:registrar",
        "historiales:archivar",
    }
)
AUTH = {"Authorization": "Bearer valido"}


def cliente(settings: Settings, unidad, permisos=TODOS) -> TestClient:
    usuario = UsuarioAutenticado("prof-1", Institucion.CLINICA_ODONTOLOGICA, permisos)
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"valido": usuario}),
        unidades_trabajo={Institucion.CLINICA_ODONTOLOGICA: lambda: unidad},
    )
    return TestClient(create_app(settings, contenedor))


def test_registrar_paciente_confirma_una_vez(settings: Settings) -> None:
    unidad = UnidadTrabajoDoble({})
    with cliente(settings, unidad) as client:
        response = client.post(
            "/api/v1/pacientes",
            json={"nombres": " Ana ", "apellidos": "Lopez", "fecha_nacimiento": "1990-05-01"},
            headers=AUTH,
        )
    assert response.status_code == 201
    assert response.json() == {
        "id_paciente": "1",
        "nombres": "Ana",
        "apellidos": "Lopez",
        "fecha_nacimiento": "1990-05-01",
        "archivado": False,
        "contacto": None,
        "alergias": None,
    }
    assert unidad.confirmaciones == 1


def test_registrar_rechaza_campos_extra_y_fecha_futura(settings: Settings) -> None:
    with cliente(settings, UnidadTrabajoDoble({})) as client:
        extra = client.post(
            "/api/v1/pacientes",
            json={"nombres": "A", "apellidos": "B", "institucion": "hospital_general"},
            headers=AUTH,
        )
        futura = client.post(
            "/api/v1/pacientes",
            json={"nombres": "A", "apellidos": "B", "fecha_nacimiento": "2999-01-01"},
            headers=AUTH,
        )
    assert extra.status_code == 422
    assert futura.status_code == 422


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo", "permiso"),
    [
        ("post", "/api/v1/pacientes", {"nombres": "A", "apellidos": "B"}, "pacientes:registrar"),
        ("get", "/api/v1/pacientes/1/historial", None, "historiales:leer"),
        ("post", "/api/v1/pacientes/1/consultas", {"motivo": "Dolor"}, "consultas:registrar"),
        ("post", "/api/v1/pacientes/1/archivo", {"motivo": "traslado"}, "historiales:archivar"),
    ],
)
def test_cada_operacion_exige_su_permiso(settings, metodo, ruta, cuerpo, permiso) -> None:
    unidad = UnidadTrabajoDoble({"1": Paciente("1", "A", "B")})
    with cliente(settings, unidad, TODOS - {permiso}) as client:
        response = client.request(metodo, ruta, json=cuerpo, headers=AUTH)
    assert response.status_code == 403
    assert unidad.confirmaciones == 0


def test_consulta_atomica_usa_profesional_del_token(settings: Settings) -> None:
    unidad = UnidadTrabajoDoble({"1": Paciente("1", "A", "B")})
    cuerpo = {
        "motivo": "Dolor molar",
        "diagnosticos": [{"descripcion": "Caries", "codigo": "K02", "sistema_codigo": "CIE-10"}],
        "tratamientos": [{"descripcion": "Obturacion"}],
        "recetas": [{"medicamento": "Ibuprofeno", "dosis": "400 mg", "frecuencia": "c/8h"}],
    }
    with cliente(settings, unidad) as client:
        response = client.post("/api/v1/pacientes/1/consultas", json=cuerpo, headers=AUTH)
    assert response.status_code == 201
    datos = response.json()
    assert datos["id_profesional"] == "prof-1"
    assert datos["diagnosticos"][0]["codigo"] == "K02"
    assert datos["recetas"][0]["medicamento"] == "Ibuprofeno"
    assert unidad.confirmaciones == 1


def test_historial_paginado_por_cursor(settings: Settings) -> None:
    historial = HistorialDoble()
    unidad = UnidadTrabajoDoble({"1": Paciente("1", "A", "B")}, historial)
    with cliente(settings, unidad) as client:
        for numero in range(3):
            client.post(
                "/api/v1/pacientes/1/consultas", json={"motivo": f"c{numero}"}, headers=AUTH
            )
        primera = client.get("/api/v1/pacientes/1/historial?limite=2", headers=AUTH).json()
        cursor = primera["siguiente_antes_de"]
        segunda = client.get(
            "/api/v1/pacientes/1/historial",
            params={"limite": 2, "antes_de": cursor},
            headers=AUTH,
        ).json()
    assert [c["motivo"] for c in primera["consultas"]] == ["c2", "c1"]
    assert cursor is not None
    assert [c["motivo"] for c in segunda["consultas"]] == ["c0"]
    assert segunda["siguiente_antes_de"] is None


def test_archivar_y_luego_bloquear_cambios(settings: Settings) -> None:
    unidad = UnidadTrabajoDoble({"1": Paciente("1", "A", "B", date(2000, 1, 1))})
    with cliente(settings, unidad) as client:
        archivo = client.post(
            "/api/v1/pacientes/1/archivo",
            json={"motivo": "traslado", "detalle": "Hospital X"},
            headers=AUTH,
        )
        repetido = client.post(
            "/api/v1/pacientes/1/archivo", json={"motivo": "traslado"}, headers=AUTH
        )
        consulta = client.post(
            "/api/v1/pacientes/1/consultas", json={"motivo": "Control"}, headers=AUTH
        )
        lectura = client.get("/api/v1/pacientes/1", headers=AUTH)
    assert archivo.status_code == 200
    assert archivo.json()["id_profesional"] == "prof-1"
    assert repetido.status_code == 409
    assert consulta.status_code == 409
    assert lectura.json()["archivado"] is True


def test_motivo_de_baja_fuera_del_catalogo_es_rechazado(settings: Settings) -> None:
    unidad = UnidadTrabajoDoble({"1": Paciente("1", "A", "B")})
    with cliente(settings, unidad) as client:
        response = client.post("/api/v1/pacientes/1/archivo", json={"motivo": "otro"}, headers=AUTH)
    assert response.status_code == 422


def test_paciente_inexistente_responde_404_en_operaciones(settings: Settings) -> None:
    with cliente(settings, UnidadTrabajoDoble({})) as client:
        historial = client.get("/api/v1/pacientes/9/historial", headers=AUTH)
        consulta = client.post("/api/v1/pacientes/9/consultas", json={"motivo": "x"}, headers=AUTH)
    assert historial.status_code == 404
    assert consulta.status_code == 404


class ConexionFalsa:
    def rollback(self) -> None: ...

    def close(self) -> None: ...


def test_operacion_no_implementada_en_un_motor_responde_501(settings: Settings) -> None:
    unidad = UnidadTrabajoSQL(lambda: ConexionFalsa(), "SELECT 1", (), motor="MySQL")
    with cliente(settings, unidad) as client:
        response = client.post(
            "/api/v1/pacientes", json={"nombres": "A", "apellidos": "B"}, headers=AUTH
        )
    assert response.status_code == 501
    assert "MySQL" in response.json()["detail"]
