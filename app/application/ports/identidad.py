from typing import Protocol

from app.domain.identidad import UsuarioAutenticado


class Autenticador(Protocol):
    def verificar_token(self, token: str) -> UsuarioAutenticado:
        """Verifica validez, expiracion e identidad; lanza TokenInvalido al fallar."""
        ...
