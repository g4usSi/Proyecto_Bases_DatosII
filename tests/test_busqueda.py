"""Busqueda de pacientes por nombre: regla comun, ruta y permisos (con dobles)."""

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain import busqueda, permisos
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.paciente import Alergia, NuevoPaciente, Paciente
from app.main import create_app
from tests.doubles import AutenticadorDoble, UnidadTrabajoDoble

LECTOR = UsuarioAutenticado(
    "u1", Institucion.CLINICA_ODONTOLOGICA, frozenset({permisos.PACIENTES_LEER})
)
SIN_PERMISO = UsuarioAutenticado("u2", Institucion.CLINICA_ODONTOLOGICA, frozenset())
H = {"Authorization": "Bearer lector"}


def cliente(settings: Settings, pacientes: dict[str, Paciente]) -> TestClient:
    unidad = UnidadTrabajoDoble(pacientes)
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"lector": LECTOR, "sin": SIN_PERMISO}),
        unidades_trabajo={Institucion.CLINICA_ODONTOLOGICA: lambda: unidad},
    )
    return TestClient(create_app(settings, contenedor))


PACIENTES = {
    "1": Paciente("1", "María José", "Pérez López"),
    "2": Paciente("2", "Marco", "Perera"),
    "3": Paciente("3", "Amaru", "Pérez", archivado=True),
    "4": Paciente("4", "Ana", "Gómez-Ruiz", alergias=(Alergia("Penicilina"),)),
}


@pytest.mark.parametrize(
    ("texto", "esperados"),
    [
        ("maria", {"1"}),
        ("MARÍA perez", {"1"}),  # sin acentos ni mayusculas
        ("mar per", {"1", "2"}),  # comienzo de palabra, todas las palabras
        ("per", {"1", "2", "3"}),
        ("ama", {"3"}),
        ("maru", set()),  # no es comienzo de palabra de nadie ("Amaru" empieza en "ama")
        ("gomez", {"4"}),
        ("ruiz", set()),  # las palabras se separan por espacios: "Gómez-Ruiz" es una sola
        ("gomez-r", {"4"}),
        ("jose lopez", {"1"}),
    ],
)
def test_regla_comun_de_busqueda(texto: str, esperados: set[str]) -> None:
    buscadas = busqueda.palabras(texto)
    obtenidos = {
        p.id_paciente
        for p in PACIENTES.values()
        if busqueda.coincide(buscadas, p.nombres, p.apellidos)
    }
    assert obtenidos == esperados


def test_prefijos_para_motores_sin_like() -> None:
    assert busqueda.prefijos_de_nombre("Ñoño", "Pérez") == [
        "n",
        "no",
        "non",
        "nono",
        "p",
        "pe",
        "per",
        "pere",
        "perez",
    ]


def test_ruta_busca_y_devuelve_resumen_sin_datos_clinicos(settings: Settings) -> None:
    with cliente(settings, dict(PACIENTES)) as client:
        response = client.get("/api/v1/pacientes", params={"nombre": "per"}, headers=H)
        limitada = client.get("/api/v1/pacientes", params={"nombre": "per", "limite": 1}, headers=H)
    assert response.status_code == 200
    filas = response.json()
    assert [f["id_paciente"] for f in filas] == ["2", "3", "1"]  # apellidos, nombres
    assert set(filas[0]) == {"id_paciente", "nombres", "apellidos", "fecha_nacimiento", "archivado"}
    assert any(f["archivado"] for f in filas)
    assert len(limitada.json()) == 1


def test_ruta_valida_y_exige_permiso(settings: Settings) -> None:
    with cliente(settings, dict(PACIENTES)) as client:
        corto = client.get("/api/v1/pacientes", params={"nombre": "a"}, headers=H)
        muchas = client.get("/api/v1/pacientes", params={"nombre": "a b c d e f g"}, headers=H)
        sin_permiso = client.get(
            "/api/v1/pacientes", params={"nombre": "maria"}, headers={"Authorization": "Bearer sin"}
        )
        anonimo = client.get("/api/v1/pacientes", params={"nombre": "maria"})
        sin_nombre = client.get("/api/v1/pacientes", headers=H)
    assert corto.status_code == 422
    assert muchas.status_code == 422
    assert sin_permiso.status_code == 403
    assert anonimo.status_code == 401
    assert sin_nombre.status_code == 422


def test_buscar_no_choca_con_consultar_por_id(settings: Settings) -> None:
    with cliente(settings, dict(PACIENTES)) as client:
        assert client.get("/api/v1/pacientes/1", headers=H).status_code == 200


def test_alergia_repetida_al_registrar_es_422(settings: Settings) -> None:
    registrar = UsuarioAutenticado(
        "u3", Institucion.CLINICA_ODONTOLOGICA, frozenset({permisos.PACIENTES_REGISTRAR})
    )
    unidad = UnidadTrabajoDoble({})
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"r": registrar}),
        unidades_trabajo={Institucion.CLINICA_ODONTOLOGICA: lambda: unidad},
    )
    with TestClient(create_app(settings, contenedor)) as client:
        repetida = client.post(
            "/api/v1/pacientes",
            json={
                "nombres": "A",
                "apellidos": "B",
                "alergias": [{"sustancia": "Penicilina"}, {"sustancia": " penicilina "}],
            },
            headers={"Authorization": "Bearer r"},
        )
    assert repetida.status_code == 422


def test_nuevo_paciente_dominio() -> None:
    assert NuevoPaciente("A", "B").alergias is None
