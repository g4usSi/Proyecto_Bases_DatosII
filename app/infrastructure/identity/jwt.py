from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.application.ports.cuentas import DirectorioProfesionales
from app.domain.cuenta import Sesion
from app.domain.errores import TokenInvalido
from app.domain.identidad import UsuarioAutenticado


class AutenticadorCentral:
    def __init__(
        self,
        directorio: DirectorioProfesionales,
        secreto: str,
        emisor: str,
        audiencia: str,
        minutos: int = 30,
    ) -> None:
        self.directorio = directorio
        self._secreto = secreto
        self.emisor = emisor
        self.audiencia = audiencia
        self.minutos = minutos
        self.passwords = PasswordHash.recommended()
        # Igualar el coste de verificacion cuando el correo no existe.
        self._hash_ficticio = self.passwords.hash(str(uuid4()))

    def iniciar_sesion(self, correo: str, password: str) -> Sesion:
        cuenta = self.directorio.buscar_por_correo(correo)
        password_hash = cuenta.password_hash if cuenta else self._hash_ficticio
        try:
            valido = self.passwords.verify(password, password_hash)
        except (UnknownHashError, ValueError):
            valido = False
        bloqueada = bool(
            cuenta and cuenta.bloqueado_hasta and cuenta.bloqueado_hasta > datetime.now(UTC)
        )
        if not valido or cuenta is None or not cuenta.activo or bloqueada:
            if cuenta and cuenta.activo and not bloqueada:
                self.directorio.registrar_login(cuenta.id_profesional, False)
            raise TokenInvalido("Credenciales invalidas.")
        self.directorio.registrar_login(cuenta.id_profesional, True)
        ahora = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": cuenta.id_profesional,
                "inst": cuenta.institucion.value if cuenta.institucion else None,
                "ver": cuenta.version_token,
                "iss": self.emisor,
                "aud": self.audiencia,
                "iat": ahora,
                "exp": ahora + timedelta(minutes=self.minutos),
                "jti": str(uuid4()),
            },
            self._secreto,
            algorithm="HS256",
        )
        return Sesion(token, self.minutos * 60, cuenta.usuario())

    def verificar_token(self, token: str) -> UsuarioAutenticado:
        try:
            payload = jwt.decode(
                token,
                self._secreto,
                algorithms=["HS256"],
                issuer=self.emisor,
                audience=self.audiencia,
                # PyJWT interpreta un claim null como ausente en `require`.
                options={"require": ["sub", "ver", "iss", "aud", "iat", "exp", "jti"]},
            )
        except jwt.InvalidTokenError as error:
            raise TokenInvalido("Token invalido.") from error
        cuenta = self.directorio.buscar_por_id(payload["sub"])
        if (
            cuenta is None
            or not cuenta.activo
            or "inst" not in payload
            or type(payload["ver"]) is not int
            or payload["ver"] != cuenta.version_token
            or payload["inst"] != (cuenta.institucion.value if cuenta.institucion else None)
            or (cuenta.bloqueado_hasta is not None and cuenta.bloqueado_hasta > datetime.now(UTC))
        ):
            raise TokenInvalido("Sesion revocada.")
        # Los permisos se leen de PostgreSQL en CADA solicitud, no del JWT.
        return cuenta.usuario()

    def cerrar_sesion(self, id_profesional: str) -> None:
        self.directorio.revocar_sesiones(id_profesional)
