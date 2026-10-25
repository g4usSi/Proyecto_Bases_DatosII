from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError


class CifradorArgon2:
    """Mismo esquema que el login (pwdlib recomendado = Argon2id)."""

    def __init__(self) -> None:
        self._hash = PasswordHash.recommended()

    def cifrar(self, contrasena: str) -> str:
        return self._hash.hash(contrasena)

    def verificar(self, contrasena: str, cifrada: str) -> bool:
        try:
            return self._hash.verify(contrasena, cifrada)
        except (UnknownHashError, ValueError):
            return False
