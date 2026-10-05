import pytest
from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.paciente import Paciente
from app.main import create_app
from tests.doubles import AutenticadorDoble, UnidadTrabajoDoble


def usuario_hospital(
    permisos: frozenset[str] = frozenset({"pacientes:leer"}),
) -> UsuarioAutenticado:
    return UsuarioAutenticado("usuario-hospital", Institucion.HOSPITAL_GENERAL, permisos)


def test_health_funciona_sin_motores(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_documentacion_expone_el_contrato_comun(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json").json()
    assert "/api/v1/pacientes/{id_paciente}" in schema["paths"]
    assert "HTTPBearer" in schema["components"]["securitySchemes"]


def test_consulta_sin_identidad_es_rechazada(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/pacientes/1")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_token_no_se_acepta_sin_autenticador(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer cualquiera"})
    assert response.status_code == 503


def test_token_invalido_es_rechazado(settings: Settings) -> None:
    contenedor = Contenedor(autenticador=AutenticadorDoble({}))
    with TestClient(create_app(settings, contenedor)) as client:
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalido"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_identidad_sin_permiso_no_accede_a_pacientes(settings: Settings) -> None:
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"valido": usuario_hospital(frozenset())})
    )
    with TestClient(create_app(settings, contenedor)) as client:
        response = client.get("/api/v1/pacientes/1", headers={"Authorization": "Bearer valido"})
    assert response.status_code == 403


def test_persistencia_pendiente_es_explicita(settings: Settings) -> None:
    contenedor = Contenedor(autenticador=AutenticadorDoble({"valido": usuario_hospital()}))
    with TestClient(create_app(settings, contenedor)) as client:
        response = client.get("/api/v1/pacientes/1", headers={"Authorization": "Bearer valido"})
    assert response.status_code == 503


@pytest.mark.parametrize("institucion", list(Institucion))
def test_enrutamiento_usa_identidad_y_aisla_ids_repetidos(
    settings: Settings, institucion: Institucion
) -> None:
    usuarios = {
        item.value: UsuarioAutenticado(item.value, item, frozenset({"pacientes:leer"}))
        for item in Institucion
    }
    contenedor = Contenedor(autenticador=AutenticadorDoble(usuarios))
    for item in Institucion:
        paciente = Paciente("1", item.value, "Paciente sintetico")
        contenedor.unidades_trabajo[item] = lambda paciente=paciente: UnidadTrabajoDoble(
            {"1": paciente}
        )

    otra = next(item for item in Institucion if item != institucion)
    with TestClient(create_app(settings, contenedor)) as client:
        response = client.get(
            "/api/v1/pacientes/1",
            headers={
                "Authorization": f"Bearer {institucion.value}",
                "X-Institucion": otra.value,
            },
        )
    assert response.status_code == 200
    assert response.json()["nombres"] == institucion.value
    assert response.json()["id_paciente"] == "1"


def test_paciente_ausente_y_liberacion_de_unidad(settings: Settings) -> None:
    unidad = UnidadTrabajoDoble({})
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"valido": usuario_hospital()}),
        unidades_trabajo={Institucion.HOSPITAL_GENERAL: lambda: unidad},
    )
    with TestClient(create_app(settings, contenedor)) as client:
        response = client.get("/api/v1/pacientes/1", headers={"Authorization": "Bearer valido"})
    assert response.status_code == 404
    assert unidad.finalizada
    assert unidad.reversiones == 1
    assert unidad.confirmaciones == 0


def test_prefijo_configurable_conserva_health(settings: Settings) -> None:
    settings = settings.model_copy(update={"api_prefix": "/v2"})
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/v2/auth/me").status_code == 401
        assert client.get("/api/v1/auth/me").status_code == 404


def test_me_devuelve_institucion_verificada(settings: Settings) -> None:
    contenedor = Contenedor(autenticador=AutenticadorDoble({"valido": usuario_hospital()}))
    with TestClient(create_app(settings, contenedor)) as client:
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer valido"})
    assert response.status_code == 200
    assert response.json()["institucion"] == "hospital_general"
    assert response.json()["permisos"] == ["pacientes:leer"]
