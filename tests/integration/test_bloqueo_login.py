from uuid import uuid4

import psycopg
import pytest
from pwdlib import PasswordHash

from app.core.config import Settings
from app.domain.errores import TokenInvalido
from app.infrastructure.identity.jwt import AutenticadorCentral
from app.infrastructure.identity.postgresql import DirectorioPostgreSQL


def test_bloqueo_persistido_y_recuperacion_tras_vencimiento(config_local):
    identificador = uuid4()
    correo = f"prueba-{identificador}@example.invalid"
    password = "Contrasena de prueba"
    settings = Settings()
    auth = AutenticadorCentral(
        DirectorioPostgreSQL(settings.postgres_dsn.get_secret_value()),
        settings.jwt_secret.get_secret_value(),
        settings.jwt_issuer,
        settings.jwt_audience,
    )
    with psycopg.connect(config_local["HISTORIALES_POSTGRES_ADMIN_DSN"], autocommit=True) as conn:
        try:
            conn.execute(
                "INSERT INTO identidad.profesional "
                "(id_profesional,correo,nombres,apellidos,password_hash,establecimiento,rol) "
                "VALUES (%s,%s,'Prueba','Sintetica',%s,'hospital_general','medico')",
                (identificador, correo, PasswordHash.recommended().hash(password)),
            )
            for _ in range(5):
                with pytest.raises(TokenInvalido):
                    auth.iniciar_sesion(correo, "incorrecta")
            row = conn.execute(
                "SELECT fallos_login,bloqueado_hasta > now() "
                "FROM identidad.profesional WHERE id_profesional=%s",
                (identificador,),
            ).fetchone()
            assert row == (5, True)
            with pytest.raises(TokenInvalido):
                auth.iniciar_sesion(correo, password)
            conn.execute(
                "UPDATE identidad.profesional SET bloqueado_hasta=now()-interval '1 second' "
                "WHERE id_profesional=%s",
                (identificador,),
            )
            assert auth.iniciar_sesion(correo, password).access_token
            assert conn.execute(
                "SELECT fallos_login,bloqueado_hasta FROM identidad.profesional "
                "WHERE id_profesional=%s",
                (identificador,),
            ).fetchone() == (0, None)
        finally:
            conn.execute(
                "DELETE FROM identidad.profesional WHERE id_profesional=%s", (identificador,)
            )
