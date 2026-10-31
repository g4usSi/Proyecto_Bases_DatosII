"""Administracion del personal en dos niveles y cambio de contrasena propio.

La identidad (correo, contrasena, permisos) vive solo en PostgreSQL. Al dar de alta o
cambiar a un profesional, ademas se actualiza su perfil local en el motor de la
institucion (sin credenciales). No es una transaccion entre motores: si ese motor no
responde, la cuenta queda creada y la respuesta lo indica (`vinculado: false`); se
completa despues con scripts/sincronizar_profesionales.py. Las cuentas de administracion
no tienen perfil local (`vinculado: null`).

Alcance: el administrador gestiona su entidad sin cuentas de administracion; el
superusuario, cualquier cuenta menos la suya, y es el unico que elimina.
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
    ESTADOS_ASIGNABLES,
    ROLES_DE_ADMINISTRACION,
    CambiosProfesional,
    EntradaBitacora,
    EstadoCuenta,
    FichaProfesional,
    FiltroBitacora,
    NuevoProfesional,
    ProfesionalAgenda,
    ResumenPersonal,
)
from app.domain.cuenta import Sesion
from app.domain.errores import (
    AccesoDenegado,
    ConflictoEstado,
    DatosInvalidos,
    ErrorDominio,
    RegistroNoEncontrado,
)
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.profesional import ProfesionalLocal

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ResultadoAlta:
    ficha: FichaProfesional
    vinculado: bool | None  # None = cuenta de administracion (no tiene perfil local)
    # Solo si no se envio contrasena: se muestra UNA vez y no se guarda.
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
        abrir_unidad: Callable[[Institucion], UnidadDeTrabajo] | None = None,
    ) -> None:
        self.directorio = directorio
        self.cifrador = cifrador
        # Abre la unidad de trabajo del motor de una institucion (perfil local).
        self.abrir_unidad = abrir_unidad

    def _vincular(self, ficha: FichaProfesional) -> bool | None:
        """Crea o actualiza el perfil local en el motor de la institucion."""
        if ficha.rol in ROLES_DE_ADMINISTRACION or ficha.institucion is None:
            return None
        if self.abrir_unidad is None:
            return False
        perfil = ProfesionalLocal(
            ficha.id_profesional,
            ficha.nombres,
            ficha.apellidos,
            ficha.rol,
            ficha.estado not in (EstadoCuenta.INACTIVA, EstadoCuenta.ELIMINADA),
        )
        try:
            with self.abrir_unidad(ficha.institucion) as unidad:
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

    def _gestionable(self, actor: UsuarioAutenticado, id_profesional: str) -> FichaProfesional:
        """La cuenta dentro del alcance del actor (404 si no, igual que si no existiera)."""
        ficha = self.directorio.obtener(reglas.alcance_de(actor), id_profesional)
        if ficha is None or not reglas.puede_gestionar(actor, ficha):
            raise RegistroNoEncontrado("El profesional no existe en tu institucion.")
        return ficha

    def crear(
        self,
        actor: UsuarioAutenticado,
        datos: NuevoProfesional,
        contrasena: str | None,
        establecimiento: Institucion | None = None,
    ) -> ResultadoAlta:
        superusuario = reglas.es_superusuario(actor)
        if superusuario:
            if establecimiento is None:
                raise DatosInvalidos("Indica el establecimiento de la cuenta nueva.")
            institucion = establecimiento
        else:
            reglas.alcance_de(actor)  # 403 si no administra una entidad
            if establecimiento is not None:
                raise DatosInvalidos(
                    "No envies establecimiento: la cuenta se crea en tu institucion."
                )
            assert actor.institucion is not None
            institucion = actor.institucion
        correo = reglas.normalizar_correo(datos.correo)
        reglas.validar_rol(institucion, datos.rol, actor_es_superusuario=superusuario)
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
            institucion, nuevo, permisos, self.cifrador.cifrar(contrasena), actor.id_usuario
        )
        return ResultadoAlta(ficha, self._vincular(ficha), temporal)

    def listar(
        self,
        actor: UsuarioAutenticado,
        rol: str | None = None,
        id_departamento: int | None = None,
        estado: EstadoCuenta | None = None,
        limite: int = 200,
        establecimiento: Institucion | None = None,
    ) -> list[FichaProfesional]:
        if estado == EstadoCuenta.ELIMINADA:
            raise DatosInvalidos("Las cuentas eliminadas no se listan.")
        alcance = reglas.alcance_de(actor, establecimiento)
        return self.directorio.listar(alcance, rol, id_departamento, estado, limite)

    def obtener(self, actor: UsuarioAutenticado, id_profesional: str) -> FichaProfesional:
        return self._gestionable(actor, id_profesional)

    def actualizar(
        self, actor: UsuarioAutenticado, id_profesional: str, cambios: CambiosProfesional
    ) -> ResultadoCambio:
        if cambios.vacio:
            raise DatosInvalidos("No enviaste ningun cambio.")
        if cambios.estado is not None and cambios.estado not in ESTADOS_ASIGNABLES:
            raise DatosInvalidos("Para eliminar una cuenta usa DELETE /profesionales/{id}.")
        actual = self._gestionable(actor, id_profesional)
        if actual.estado == EstadoCuenta.ELIMINADA:
            raise ConflictoEstado("La cuenta fue eliminada: ya no se puede modificar.")
        assert actual.institucion is not None
        reglas.validar_departamento(actual.institucion, cambios.id_departamento)
        permisos = (
            reglas.permisos_finales(actual.institucion, actual.rol, cambios.permisos)
            if cambios.permisos is not None
            else None
        )
        ficha = self.directorio.actualizar(
            reglas.alcance_de(actor), id_profesional, cambios, permisos, actor.id_usuario
        )
        perfil_cambio = (
            ficha.nombres != actual.nombres
            or ficha.apellidos != actual.apellidos
            or (ficha.estado == EstadoCuenta.INACTIVA) != (actual.estado == EstadoCuenta.INACTIVA)
        )
        return ResultadoCambio(ficha, self._vincular(ficha) if perfil_cambio else None)

    def eliminar(self, actor: UsuarioAutenticado, id_profesional: str) -> FichaProfesional:
        """Baja definitiva logica. Solo el superusuario; nunca sobre si mismo."""
        if not reglas.es_superusuario(actor):
            raise AccesoDenegado("Solo la administracion general elimina cuentas.")
        actual = self._gestionable(actor, id_profesional)
        if actual.estado == EstadoCuenta.ELIMINADA:
            raise ConflictoEstado("La cuenta ya estaba eliminada.")
        self.directorio.eliminar(reglas.alcance_de(actor), id_profesional, actor.id_usuario)
        eliminada = self.directorio.obtener(reglas.alcance_de(actor), id_profesional)
        if eliminada is not None:
            self._vincular(eliminada)  # el perfil local queda inactivo
        return eliminada or actual

    def restablecer_contrasena(self, actor: UsuarioAutenticado, id_profesional: str) -> str:
        """Genera una contrasena nueva (se muestra una sola vez) y cierra sus sesiones."""
        actual = self._gestionable(actor, id_profesional)  # 404 fuera del alcance
        if actual.estado == EstadoCuenta.ELIMINADA:
            raise ConflictoEstado("La cuenta fue eliminada: ya no se puede modificar.")
        nueva = reglas.generar_contrasena()
        self.directorio.establecer_contrasena(
            id_profesional,
            self.cifrador.cifrar(nueva),
            debe_cambiar=True,
            id_actor=actor.id_usuario,
            accion="restablecer_contrasena",
        )
        return nueva

    def resumen(
        self, actor: UsuarioAutenticado, establecimiento: Institucion | None = None
    ) -> ResumenPersonal:
        alcance = reglas.alcance_de(actor, establecimiento)
        if alcance.institucion is None:
            raise DatosInvalidos("Indica el establecimiento del resumen.")
        return self.directorio.resumen(alcance.institucion)

    def bitacora(
        self,
        actor: UsuarioAutenticado,
        filtro: FiltroBitacora,
        establecimiento: Institucion | None = None,
    ) -> list[EntradaBitacora]:
        if filtro.desde and filtro.hasta and filtro.desde >= filtro.hasta:
            raise DatosInvalidos("'desde' debe ser anterior a 'hasta'.")
        return self.directorio.bitacora(reglas.alcance_de(actor, establecimiento), filtro)

    def para_agenda(self, usuario: UsuarioAutenticado) -> list[ProfesionalAgenda]:
        if usuario.institucion is None:
            raise AccesoDenegado("La administracion general no agenda citas.")
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
