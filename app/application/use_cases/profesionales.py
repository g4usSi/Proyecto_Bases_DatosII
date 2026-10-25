"""Administracion del personal y cambio de contrasena propio.

La identidad (correo, contrasena, permisos) vive solo en PostgreSQL. Al dar de alta o
cambiar a un profesional, ademas se actualiza su perfil local en el motor de la
institucion (sin credenciales). No es una transaccion entre motores: si ese motor no
responde, la cuenta queda creada y la respuesta lo indica (`vinculado: false`); se
completa despues con scripts/sincronizar_profesionales.py.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from app.application.errores import IntegracionNoConfigurada, OperacionPendiente
from app.application.ports.administracion import Cifrador, DirectorioAdministrable
from app.application.ports.cuentas import DirectorioProfesionales, InicioSesion
from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain import administracion as reglas
from app.domain.administracion import (
    CambiosProfesional,
    EstadoCuenta,
    FichaProfesional,
    NuevoProfesional,
    ProfesionalAgenda,
)
from app.domain.cuenta import Sesion
from app.domain.errores import DatosInvalidos, ErrorDominio, RegistroNoEncontrado
from app.domain.identidad import UsuarioAutenticado
from app.domain.profesional import ProfesionalLocal

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResultadoAlta:
    ficha: FichaProfesional
    vinculado: bool
    # Solo si el administrador no envio contrasena: se muestra UNA vez y no se guarda.
    contrasena_temporal: str | None = None


@dataclass(frozen=True, slots=True)
class ResultadoCambio:
    ficha: FichaProfesional
    vinculado: bool | None  # None = no hacia falta tocar el perfil local


class AdministrarProfesionales:
    def __init__(
        self,
        directorio: DirectorioAdministrable,
        cifrador: Cifrador,
        abrir_unidad: Callable[[], UnidadDeTrabajo] | None = None,
    ) -> None:
        self.directorio = directorio
        self.cifrador = cifrador
        self.abrir_unidad = abrir_unidad

    def _vincular(self, ficha: FichaProfesional) -> bool:
        """Crea o actualiza el perfil local en el motor de la institucion."""
        if self.abrir_unidad is None:
            return False
        perfil = ProfesionalLocal(
            ficha.id_profesional,
            ficha.nombres,
            ficha.apellidos,
            ficha.rol,
            ficha.estado != EstadoCuenta.INACTIVA,
        )
        try:
            with self.abrir_unidad() as unidad:
                unidad.profesionales.sincronizar(perfil)
                unidad.commit()
        except (IntegracionNoConfigurada, OperacionPendiente, ErrorDominio) as error:
            logger.warning(
                "No se vinculo el perfil local de %s (%s); repetir con "
                "python -m scripts.sincronizar_profesionales",
                ficha.id_profesional,
                type(error).__name__,
            )
            return False
        return True

    def crear(
        self, admin: UsuarioAutenticado, datos: NuevoProfesional, contrasena: str | None
    ) -> ResultadoAlta:
        institucion = admin.institucion
        correo = reglas.normalizar_correo(datos.correo)
        reglas.validar_rol(institucion, datos.rol)
        permisos = reglas.permisos_finales(institucion, datos.rol, datos.permisos)
        reglas.validar_departamento(institucion, datos.id_departamento)
        temporal = None
        if contrasena is None:
            temporal = contrasena = reglas.generar_contrasena()
        reglas.validar_contrasena(contrasena, correo)
        nuevo = NuevoProfesional(
            correo,
            datos.nombres,
            datos.apellidos,
            datos.rol,
            permisos,
            datos.id_departamento,
        )
        ficha = self.directorio.crear(
            institucion, nuevo, permisos, self.cifrador.cifrar(contrasena), admin.id_usuario
        )
        return ResultadoAlta(ficha, self._vincular(ficha), temporal)

    def listar(
        self,
        admin: UsuarioAutenticado,
        rol: str | None = None,
        id_departamento: int | None = None,
        estado: EstadoCuenta | None = None,
        limite: int = 200,
    ) -> list[FichaProfesional]:
        return self.directorio.listar(admin.institucion, rol, id_departamento, estado, limite)

    def obtener(self, admin: UsuarioAutenticado, id_profesional: str) -> FichaProfesional:
        ficha = self.directorio.obtener(admin.institucion, id_profesional)
        if ficha is None:
            raise RegistroNoEncontrado("El profesional no existe en tu institucion.")
        return ficha

    def actualizar(
        self, admin: UsuarioAutenticado, id_profesional: str, cambios: CambiosProfesional
    ) -> ResultadoCambio:
        if cambios.vacio:
            raise DatosInvalidos("No enviaste ningun cambio.")
        actual = self.obtener(admin, id_profesional)
        reglas.validar_departamento(admin.institucion, cambios.id_departamento)
        permisos = (
            reglas.permisos_finales(admin.institucion, actual.rol, cambios.permisos)
            if cambios.permisos is not None
            else None
        )
        ficha = self.directorio.actualizar(
            admin.institucion, id_profesional, cambios, permisos, admin.id_usuario
        )
        perfil_cambio = (
            ficha.nombres != actual.nombres
            or ficha.apellidos != actual.apellidos
            or (ficha.estado == EstadoCuenta.INACTIVA) != (actual.estado == EstadoCuenta.INACTIVA)
        )
        return ResultadoCambio(ficha, self._vincular(ficha) if perfil_cambio else None)

    def restablecer_contrasena(self, admin: UsuarioAutenticado, id_profesional: str) -> str:
        """Genera una contrasena nueva (se muestra una sola vez) y cierra sus sesiones."""
        self.obtener(admin, id_profesional)  # 404 si no es de su institucion
        nueva = reglas.generar_contrasena()
        self.directorio.establecer_contrasena(
            id_profesional,
            self.cifrador.cifrar(nueva),
            debe_cambiar=True,
            id_actor=admin.id_usuario,
            accion="restablecer_contrasena",
        )
        return nueva

    def para_agenda(self, usuario: UsuarioAutenticado) -> list[ProfesionalAgenda]:
        return self.directorio.listar_para_agenda(usuario.institucion)


class CambiarContrasena:
    """La persona cambia su propia contrasena. Revoca sus otras sesiones y abre una nueva."""

    def __init__(
        self,
        cuentas: DirectorioProfesionales,
        directorio: DirectorioAdministrable,
        cifrador: Cifrador,
        inicio_sesion: InicioSesion,
    ) -> None:
        self.cuentas = cuentas
        self.directorio = directorio
        self.cifrador = cifrador
        self.inicio_sesion = inicio_sesion

    def ejecutar(self, usuario: UsuarioAutenticado, actual: str, nueva: str) -> Sesion:
        cuenta = self.cuentas.buscar_por_id(usuario.id_usuario)
        if cuenta is None:
            raise RegistroNoEncontrado("La cuenta no existe.")
        if not self.cifrador.verificar(actual, cuenta.password_hash):
            # Cuenta como intento fallido: el bloqueo por intentos tambien protege esta ruta.
            self.cuentas.registrar_login(cuenta.id_profesional, False)
            raise DatosInvalidos("La contrasena actual no es correcta.")
        if actual == nueva:
            raise DatosInvalidos("La contrasena nueva debe ser distinta de la actual.")
        reglas.validar_contrasena(nueva, cuenta.correo)
        self.directorio.establecer_contrasena(
            cuenta.id_profesional,
            self.cifrador.cifrar(nueva),
            debe_cambiar=False,
            id_actor=cuenta.id_profesional,
            accion="cambiar_contrasena",
        )
        return self.inicio_sesion.iniciar_sesion(cuenta.correo, nueva)
