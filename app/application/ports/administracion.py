from datetime import datetime
from typing import Protocol

from app.domain.administracion import (
    CambiosProfesional,
    EstadoCuenta,
    EventoProfesional,
    FichaProfesional,
    NuevoProfesional,
    ProfesionalAgenda,
    ResumenPersonal,
)
from app.domain.institucion import Institucion


class Cifrador(Protocol):
    """Hash de contrasenas (Argon2id). La API nunca guarda ni devuelve la contrasena."""

    def cifrar(self, contrasena: str) -> str: ...

    def verificar(self, contrasena: str, cifrada: str) -> bool: ...


class DirectorioAdministrable(Protocol):
    """Cuentas centrales: alcance institucional o global autorizado por el caso de uso.

    Cada escritura deja su evento en la bitacora de administracion dentro de la misma
    transaccion: o se guardan ambos, o ninguno.
    """

    def crear(
        self,
        institucion: Institucion,
        datos: NuevoProfesional,
        permisos: frozenset[str],
        contrasena_cifrada: str,
        id_actor: str,
    ) -> FichaProfesional:
        """ConflictoEstado si el correo ya existe; DatosInvalidos si el area no existe."""
        ...

    def listar(
        self,
        institucion: Institucion | None,
        rol: str | None = None,
        id_departamento: int | None = None,
        estado: EstadoCuenta | None = None,
        limite: int = 200,
        incluir_administradores: bool = False,
    ) -> list[FichaProfesional]:
        """Por apellidos. Plataforma puede incluir administradores con alcance global."""
        ...

    def obtener(
        self,
        institucion: Institucion | None,
        id_profesional: str,
        incluir_administradores: bool = False,
        incluir_eliminados: bool = False,
    ) -> FichaProfesional | None:
        """None si no existe, es de otra institucion o es una cuenta de administracion."""
        ...

    def eliminar(self, id_profesional: str, id_actor: str) -> None: ...

    def consultar_bitacora(
        self,
        institucion: Institucion | None,
        accion: str | None = None,
        desde: datetime | None = None,
        hasta: datetime | None = None,
        limite: int = 50,
        antes_de: int | None = None,
    ) -> list[EventoProfesional]: ...

    def resumen(self, institucion: Institucion) -> ResumenPersonal: ...

    def actualizar(
        self,
        institucion: Institucion,
        id_profesional: str,
        cambios: CambiosProfesional,
        permisos: frozenset[str] | None,
        id_actor: str,
    ) -> FichaProfesional:
        """Aplica los cambios. Bloquear o desactivar revoca de inmediato las sesiones."""
        ...

    def establecer_contrasena(
        self,
        id_profesional: str,
        contrasena_cifrada: str,
        debe_cambiar: bool,
        id_actor: str,
        accion: str,
    ) -> None:
        """Reemplaza el hash y revoca todas las sesiones de esa cuenta."""
        ...

    def listar_para_agenda(self, institucion: Institucion) -> list[ProfesionalAgenda]:
        """Profesionales activos que atienden pacientes (sin secretaria ni administracion)."""
        ...
