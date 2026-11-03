from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.cuenta import CuentaProfesional
from app.domain.errores import TokenInvalido
from app.domain.institucion import Institucion
from app.infrastructure.identity.jwt import AutenticadorCentral
from app.main import create_app

SECRETO = "secreto-exclusivo-para-pruebas-" + "x" * 32
PASSWORD = "Password de prueba privado"


class DirectorioDoble:
    def __init__(self, cuenta: CuentaProfesional):
        self.cuenta = cuenta

    def buscar_por_correo(self, correo: str) -> CuentaProfesional | None:
        return self.cuenta if correo.strip().lower() == self.cuenta.correo else None

    def buscar_por_id(self, identificador: str) -> CuentaProfesional | None:
        return self.cuenta if identificador == self.cuenta.id_profesional else None

    def revocar_sesiones(self, identificador: str) -> None:
        self.cuenta = replace(self.cuenta, version_token=self.cuenta.version_token + 1)

    def registrar_login(self, identificador: str, exitoso: bool) -> None:
        pass  # El bloqueo persistido se verifica en las pruebas de PostgreSQL.


@pytest.fixture
def autenticador() -> AutenticadorCentral:
    cuenta = CuentaProfesional(
        str(uuid4()),
        "profesional@example.invalid",
        PasswordHash.recommended().hash(PASSWORD),
        Institucion.CENTRO_PEDIATRICO,
        frozenset({"pacientes:leer"}),
        0,
        True,
    )
    return AutenticadorCentral(DirectorioDoble(cuenta), SECRETO, "pruebas", "api-pruebas")


def test_login_y_logout_revocan_sesion(settings: Settings, autenticador: AutenticadorCentral):
    contenedor = Contenedor(autenticador=autenticador, inicio_sesion=autenticador)
    with TestClient(create_app(settings, contenedor)) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "correo": " PROFESIONAL@example.invalid ",
                "password": PASSWORD,
            },
        )
        assert login.status_code == 200
        assert login.headers["cache-control"] == "no-store"
        assert login.json()["usuario"]["institucion"] == "centro_pediatrico"
        assert "password_hash" not in login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


@pytest.mark.parametrize("caso", ["inexistente", "password_incorrecto", "inactivo"])
def test_credenciales_fallidas_no_revelan_si_existe_cuenta(
    settings: Settings,
    autenticador: AutenticadorCentral,
    caso: str,
):
    correo = "profesional@example.invalid" if caso != "inexistente" else "nadie@example.invalid"
    password = "incorrecto" if caso == "password_incorrecto" else PASSWORD
    if caso == "inactivo":
        autenticador.directorio.cuenta = replace(autenticador.directorio.cuenta, activo=False)
    contenedor = Contenedor(autenticador=autenticador, inicio_sesion=autenticador)
    with TestClient(create_app(settings, contenedor)) as client:
        response = client.post("/api/v1/auth/login", json={"correo": correo, "password": password})
    assert response.status_code == 401
    assert response.json() == {"detail": "Correo o contrasena invalidos."}


@pytest.mark.parametrize("cambio", ["desactivar", "mover", "revocar"])
def test_cambios_en_directorio_invalidan_token(autenticador: AutenticadorCentral, cambio: str):
    token = autenticador.iniciar_sesion("profesional@example.invalid", PASSWORD).access_token
    campos = {
        "desactivar": {"activo": False},
        "mover": {"institucion": Institucion.HOSPITAL_GENERAL},
        "revocar": {"version_token": 1},
    }[cambio]
    autenticador.directorio.cuenta = replace(autenticador.directorio.cuenta, **campos)
    with pytest.raises(TokenInvalido):
        autenticador.verificar_token(token)


def test_permisos_se_actualizan_sin_esperar_expiracion(autenticador: AutenticadorCentral):
    token = autenticador.iniciar_sesion("profesional@example.invalid", PASSWORD).access_token
    autenticador.directorio.cuenta = replace(autenticador.directorio.cuenta, permisos=frozenset())
    assert autenticador.verificar_token(token).permisos == frozenset()


@pytest.mark.parametrize("cambio", ["expirado", "firma", "emisor", "audiencia", "algoritmo"])
def test_token_estricto(autenticador: AutenticadorCentral, cambio: str):
    token = autenticador.iniciar_sesion("profesional@example.invalid", PASSWORD).access_token
    payload = jwt.decode(token, SECRETO, algorithms=["HS256"], audience="api-pruebas")
    if cambio == "expirado":
        payload["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    if cambio == "emisor":
        payload["iss"] = "otro"
    if cambio == "audiencia":
        payload["aud"] = "otra"
    token = jwt.encode(
        payload,
        "otra-firma-con-longitud-suficiente" if cambio == "firma" else SECRETO,
        algorithm="HS384" if cambio == "algoritmo" else "HS256",
    )
    with pytest.raises(TokenInvalido):
        autenticador.verificar_token(token)


def test_cliente_no_elige_institucion_y_validacion_no_refleja_password(
    settings: Settings,
    autenticador: AutenticadorCentral,
):
    contenedor = Contenedor(autenticador=autenticador, inicio_sesion=autenticador)
    with TestClient(create_app(settings, contenedor)) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "correo": "profesional@example.invalid",
                "password": PASSWORD,
                "institucion": "hospital_general",
            },
        )
        invalido = client.post(
            "/api/v1/auth/login",
            json={
                "correo": "profesional@example.invalid",
                "password": PASSWORD * 100,
            },
        )
    assert response.status_code == invalido.status_code == 422
    assert PASSWORD not in invalido.text


def test_token_del_superusuario_lleva_inst_null_y_no_abre_motores(settings: Settings):
    cuenta = CuentaProfesional(
        str(uuid4()),
        "super@example.invalid",
        PasswordHash.recommended().hash(PASSWORD),
        None,
        frozenset({"plataforma:administrar", "pagos:ver"}),
        0,
        True,
        rol="superusuario",
    )
    directorio = DirectorioDoble(cuenta)
    autenticador = AutenticadorCentral(directorio, SECRETO, "pruebas", "api-pruebas")
    sesion = autenticador.iniciar_sesion(cuenta.correo, PASSWORD)
    payload = jwt.decode(sesion.access_token, SECRETO, algorithms=["HS256"], audience="api-pruebas")
    assert "inst" in payload and payload["inst"] is None
    assert autenticador.verificar_token(sesion.access_token).institucion is None
    # Un token sin el claim "inst" se rechaza aunque este firmado.
    sin_inst = {k: v for k, v in payload.items() if k != "inst"}
    with pytest.raises(TokenInvalido):
        autenticador.verificar_token(jwt.encode(sin_inst, SECRETO, algorithm="HS256"))
    # Si la cuenta pasa a tener entidad, el token anterior deja de valer.
    directorio.cuenta = replace(cuenta, institucion=Institucion.HOSPITAL_GENERAL)
    with pytest.raises(TokenInvalido):
        autenticador.verificar_token(sesion.access_token)
    directorio.cuenta = cuenta
    contenedor = Contenedor(autenticador=autenticador, inicio_sesion=autenticador)
    with TestClient(create_app(settings, contenedor)) as client:
        h = {"Authorization": f"Bearer {sesion.access_token}"}
        assert client.get("/api/v1/auth/me", headers=h).json()["institucion"] is None
        assert client.get("/api/v1/pacientes/1", headers=h).status_code == 403
