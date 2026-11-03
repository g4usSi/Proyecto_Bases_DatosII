from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.cuentas_demo import inicializar_cuentas_demo
from app.core.config import Settings
from app.main import create_app
from scripts.aplicar_migracion import main


@pytest.mark.parametrize(
    "opciones",
    [
        {"environment": "produccion"},
        {"environment": "pruebas"},
        {"cuentas_demo": False},
        {"postgres_dsn": None, "jwt_secret": None},
    ],
)
def test_demo_desactivado_no_conecta_ni_imprime(opciones, capsys):
    settings = Settings(_env_file=None, **opciones)
    with patch("app.bootstrap.cuentas_demo.psycopg.connect") as conectar:
        inicializar_cuentas_demo(settings)
    conectar.assert_not_called()
    assert not capsys.readouterr().out


def test_arranque_invoca_inicializacion(settings):
    with patch("app.main.inicializar_cuentas_demo") as inicializar:
        with TestClient(create_app(settings)):
            inicializar.assert_called_once_with(settings)


def test_migracion_fallida_no_anuncia_exito_ni_ejecuta_seed(monkeypatch, capsys):
    import subprocess

    monkeypatch.setattr("sys.argv", ["migrar", "database/postgresql/016_frontend_hospital.sql"])
    with patch("scripts.aplicar_migracion.subprocess.run") as ejecutar:
        ejecutar.side_effect = subprocess.CalledProcessError(1, "docker")
        with pytest.raises(SystemExit, match="1"):
            main()
    assert ejecutar.call_count == 1
    assert "verificadas" not in capsys.readouterr().out
