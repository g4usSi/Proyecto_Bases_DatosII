"""Tutores con dobles: 501 fuera del Centro Pediatrico y validaciones de entrada."""

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.errores import DatosInvalidos
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.paciente import Paciente
from app.domain.tutores import CambiosTutor, Vinculo, nombre_de_religion
from app.main import create_app
from tests.doubles import AutenticadorDoble, UnidadTrabajoDoble

H = {"Authorization": "Bearer t"}


@pytest.fixture
def client(settings: Settings):
    usuario = UsuarioAutenticado(
        "u1", Institucion.HOSPITAL_GENERAL, frozenset({"pacientes:leer", "pacientes:registrar"})
    )
    unidad = UnidadTrabajoDoble({"1": Paciente("1", "Ana", "Lopez")})
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"t": usuario}),
        unidades_trabajo={Institucion.HOSPITAL_GENERAL: lambda: unidad},
    )
    with TestClient(create_app(settings, contenedor)) as cliente:
        yield cliente


def test_fuera_del_centro_pediatrico_responde_501(client) -> None:
    lista = client.get("/api/v1/pacientes/1/tutores", headers=H)
    nuevo = client.post(
        "/api/v1/pacientes/1/tutores", json={"id_tutor": "3", "parentesco": "Madre"}, headers=H
    )
    assert lista.status_code == 501 and "Centro Pediatrico" in lista.text
    assert nuevo.status_code == 501


def test_validaciones(client) -> None:
    ambos = client.post(
        "/api/v1/pacientes/1/tutores",
        json={"id_tutor": "3", "tutor": {"nombres": "A", "apellidos": "B"}, "parentesco": "X"},
        headers=H,
    )
    principal_no_autorizado = client.post(
        "/api/v1/pacientes/1/tutores",
        json={"id_tutor": "3", "parentesco": "X", "es_principal": True, "autorizado": False},
        headers=H,
    )
    assert ambos.status_code == 422 and principal_no_autorizado.status_code == 422


def test_reglas_del_vinculo() -> None:
    Vinculo("Madre", es_principal=True).validar()
    with pytest.raises(DatosInvalidos):
        Vinculo("Madre", es_principal=True, autorizado=False).validar()
    with pytest.raises(DatosInvalidos):
        Vinculo("  ").validar()
    assert CambiosTutor().vacio and not CambiosTutor(autorizado=False).vacio


def test_religion_del_tutor_se_valida_y_fuera_del_centro_es_501(client) -> None:
    larga = client.post(
        "/api/v1/pacientes/1/tutores",
        json={
            "tutor": {"nombres": "A", "apellidos": "B", "religion": "x" * 101},
            "parentesco": "X",
        },
        headers=H,
    )
    assert larga.status_code == 422
    assert client.get("/api/v1/religiones", headers=H).status_code == 501


def test_religion_normalizada_y_cambio_solo_de_religion() -> None:
    assert nombre_de_religion("  Iglesia   evangelica ") == "Iglesia evangelica"
    assert nombre_de_religion("   ") is None and nombre_de_religion(None) is None
    assert CambiosTutor(religion="").vacio is False  # "" borra la religion: si es un cambio
