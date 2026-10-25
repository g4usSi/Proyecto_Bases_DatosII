from collections.abc import Callable
from dataclasses import dataclass, field

from app.application.errores import IntegracionNoConfigurada
from app.application.ports.administracion import Cifrador, DirectorioAdministrable
from app.application.ports.cuentas import DirectorioProfesionales, InicioSesion
from app.application.ports.identidad import Autenticador
from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.institucion import Institucion


@dataclass
class Contenedor:
    autenticador: Autenticador | None = None
    inicio_sesion: InicioSesion | None = None
    # Administracion de cuentas (identidad central en PostgreSQL).
    cuentas: DirectorioProfesionales | None = None
    administracion: DirectorioAdministrable | None = None
    cifrador: Cifrador | None = None
    unidades_trabajo: dict[Institucion, Callable[[], UnidadDeTrabajo]] = field(default_factory=dict)
    cierres: list[Callable[[], None]] = field(default_factory=list)
    # Una por institucion: abre una conexion y hace un ping; lanza si el motor no responde.
    verificaciones: dict[Institucion, Callable[[], None]] = field(default_factory=dict)

    def cerrar(self) -> None:
        for cierre in self.cierres:
            cierre()

    def crear_unidad_trabajo(self, institucion: Institucion) -> UnidadDeTrabajo:
        fabrica = self.unidades_trabajo.get(institucion)
        if fabrica is None:
            raise IntegracionNoConfigurada(
                "La persistencia de tu institucion todavia no esta configurada."
            )
        return fabrica()
