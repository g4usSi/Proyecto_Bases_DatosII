from typing import Protocol

from app.domain.administracion import (
    Alcance,
    CambiosProfesional,
    EntradaBitacora,
    EstadoCuenta,
    FichaProfesional,
    FiltroBitacora,
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
    """Cuentas de la identidad central, siempre acotadas a un Alcance.

    El alcance del administrador es su institucion sin cuentas de administracion; el del
    superusuario, todas las entidades (o la pedida) con sus administradores. El superusuario
    nunca aparece. Cada escritura deja su evento en la bitacora de administracion dentro de
    la misma transaccion: o se guardan ambos, o ninguno.
    """

    def crear(
        self,
        institucion: Institucion,
        datos: NuevoProfesional,
        permisos: frozenset[str],
        contrasena_cifrada: str,
        id_actor: str,
    ) -> FichaProfesional:
        """ConflictoEstado si el correo ya existe o la entidad ya tiene un administrador
        activo; DatosInvalidos si el area no existe."""
        ...

    def listar(
        self,
        alcance: Alcance,
        rol: str | None = None,
        id_departamento: int | None = None,
        estado: EstadoCuenta | None = None,
        limite: int = 200,
    ) -> list[FichaProfesional]:
        """Cuentas del alcance, sin eliminadas, por entidad y apellidos."""
        ...

    def obtener(self, alcance: Alcance, id_profesional: str) -> FichaProfesional | None:
        """None si no existe o esta fuera del alcance. Una eliminada se devuelve con estado
        `eliminada` (para responder 409 a sus cambios)."""
        ...

    def actualizar(
        self,
        alcance: Alcance,
        id_profesional: str,
        cambios: CambiosProfesional,
        permisos: frozenset[str] | None,
        id_actor: str,
    ) -> FichaProfesional:
        """Aplica los cambios. Bloquear o desactivar revoca de inmediato las sesiones.
        ConflictoEstado si la cuenta esta eliminada o se rehabilita un segundo administrador."""
        ...

    def eliminar(self, alcance: Alcance, id_profesional: str, id_actor: str) -> None:
        """Baja definitiva logica: inactiva, fecha de baja, sesiones revocadas y bitacora.
        RegistroNoEncontrado fuera del alcance; ConflictoEstado si ya estaba eliminada."""
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

    def resumen(self, institucion: Institucion) -> ResumenPersonal:
        """Conteos del personal de una entidad y sus ultimos movimientos."""
        ...

    def bitacora(self, alcance: Alcance, filtro: FiltroBitacora) -> list[EntradaBitacora]:
        """Movimientos del alcance, del mas reciente al mas antiguo."""
        ...
