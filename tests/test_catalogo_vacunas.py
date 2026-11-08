"""Catalogo de vacunas con dobles: permisos, 501 y validaciones."""

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.errores import DatosInvalidos
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.paciente import Paciente
from app.domain.pediatria import DescripcionVacuna, nombre_de_vacuna
from app.main import create_app
from tests.doubles import AutenticadorDoble, UnidadTrabajoDoble

ADMIN = {"Authorization": "Bearer admin"}
MEDICO = {"Authorization": "Bearer medico"}
SUPER = {"Authorization": "Bearer super"}


@pytest.fixture
def client(settings: Settings):
    """Hospital General: aqui el catalogo de vacunas no existe (501)."""
    usuarios = {
        "admin": UsuarioAutenticado(
            "a1", Institucion.HOSPITAL_GENERAL, frozenset({"profesionales:administrar"})
        ),
        "medico": UsuarioAutenticado(
            "m1",
            Institucion.HOSPITAL_GENERAL,
            frozenset({"historiales:leer", "pacientes:leer", "pacientes:registrar"}),
        ),
        "super": UsuarioAutenticado(
            "s1", None, frozenset({"plataforma:administrar", "profesionales:administrar"})
        ),
    }
    unidad = UnidadTrabajoDoble({"1": Paciente("1", "Ana", "Lopez")})
    contenedor = Contenedor(
        autenticador=AutenticadorDoble(usuarios),
        unidades_trabajo={Institucion.HOSPITAL_GENERAL: lambda: unidad},
    )
    with TestClient(create_app(settings, contenedor)) as cliente:
        yield cliente


VACUNA = {"nombre": "BCG", "edad_recomendada_meses": 0, "dosis_sugerida": "Dosis unica"}


def test_solo_el_administrador_agrega_o_corrige_vacunas(client) -> None:
    assert client.post("/api/v1/vacunas", json=VACUNA, headers=MEDICO).status_code == 403
    assert client.put("/api/v1/vacunas/1", json={}, headers=MEDICO).status_code == 403
    # El superusuario no tiene institucion: no mantiene catalogos clinicos.
    assert client.post("/api/v1/vacunas", json=VACUNA, headers=SUPER).status_code == 403
    # Fuera del Centro Pediatrico el catalogo no existe.
    respuesta = client.post("/api/v1/vacunas", json=VACUNA, headers=ADMIN)
    assert respuesta.status_code == 501 and "Centro Pediatrico" in respuesta.text
    assert client.get("/api/v1/vacunas", headers=ADMIN).status_code == 501
    assert client.put("/api/v1/vacunas/1", json={}, headers=ADMIN).status_code == 501


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"nombre": "  "},
        {"nombre": "X" * 151},
        {"nombre": "X", "edad_recomendada_meses": -1},
        {"nombre": "X", "edad_recomendada_meses": 217},
        {"nombre": "X", "dosis_sugerida": "x" * 101},
        {"nombre": "X", "lote": "A1"},
    ],
)
def test_validaciones_al_agregar_una_vacuna(client, cuerpo) -> None:
    assert client.post("/api/v1/vacunas", json=cuerpo, headers=ADMIN).status_code == 422


def test_el_nombre_no_se_cambia_y_el_id_es_numerico(client) -> None:
    assert client.put("/api/v1/vacunas/1", json={"nombre": "Otra"}, headers=ADMIN).status_code == (
        422
    )
    assert client.put("/api/v1/vacunas/abc", json={}, headers=ADMIN).status_code == 422


def test_reglas_de_la_descripcion_y_del_nombre() -> None:
    DescripcionVacuna(edad_recomendada_meses=0).validar()
    DescripcionVacuna(edad_recomendada_meses=216).validar()
    for edad in (-1, 217):
        with pytest.raises(DatosInvalidos):
            DescripcionVacuna(edad_recomendada_meses=edad).validar()
    assert nombre_de_vacuna("  Neumococo   conjugada ") == "Neumococo conjugada"
    with pytest.raises(DatosInvalidos):
        nombre_de_vacuna("   ")
