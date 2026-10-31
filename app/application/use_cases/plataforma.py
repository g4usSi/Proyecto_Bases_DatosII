"""Resumen de la plataforma para el superusuario: SOLO conteos de las cuatro entidades.

La identidad central (PostgreSQL) da el personal de cada entidad; el motor de cada entidad
da sus propios conteos. Los motores se consultan en paralelo y con un plazo: si uno no
responde (o tarda), su entidad sale con `indicadores = None` y las demas no se bloquean.
"""

import logging
import time as reloj
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as PlazoVencido
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.application.ports.administracion import DirectorioAdministrable
from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.administracion import EstadoCuenta
from app.domain.cita import EstadoCita
from app.domain.institucion import Institucion
from app.domain.plataforma import IndicadoresEntidad, ResumenEntidad, ResumenPlataforma

logger = logging.getLogger(__name__)

ORDEN = (
    Institucion.HOSPITAL_GENERAL,
    Institucion.CENTRO_PEDIATRICO,
    Institucion.LABORATORIO_CLINICO,
    Institucion.CLINICA_ODONTOLOGICA,
)


class ResumenDePlataforma:
    def __init__(
        self,
        directorio: DirectorioAdministrable,
        abrir_unidad: Callable[[Institucion], UnidadDeTrabajo],
        zona: ZoneInfo,
        plazo_segundos: float = 6.0,
    ) -> None:
        self.directorio = directorio
        self.abrir_unidad = abrir_unidad
        self.zona = zona
        self.plazo = plazo_segundos

    def _citas(self, unidad: UnidadDeTrabajo, desde: datetime, hasta: datetime) -> int:
        return sum(
            1
            for cita in unidad.citas.listar_agenda(desde, hasta)
            if cita.estado != EstadoCita.CANCELADA
        )

    def _indicadores(self, institucion: Institucion, hoy: date) -> IndicadoresEntidad:
        inicio_dia = datetime.combine(hoy, time.min, tzinfo=self.zona)
        lunes = inicio_dia - timedelta(days=hoy.weekday())
        with self.abrir_unidad(institucion) as unidad:
            indicadores = unidad.indicadores.conteos(hoy)
            return replace(
                indicadores,
                citas_hoy=self._citas(unidad, inicio_dia, inicio_dia + timedelta(days=1)),
                citas_semana=self._citas(unidad, lunes, lunes + timedelta(days=7)),
            )

    def ejecutar(self) -> ResumenPlataforma:
        hoy = datetime.now(self.zona).date()
        # Primero la identidad central: si no responde, el resumen no tiene sentido (503).
        personal = {i: self.directorio.resumen(i) for i in ORDEN}
        # Sin "with": su salida esperaria al motor lento y anularia el plazo.
        hilos = ThreadPoolExecutor(max_workers=len(ORDEN), thread_name_prefix="resumen")
        indicadores: dict[Institucion, IndicadoresEntidad | None] = {}
        try:
            futuros = {i: hilos.submit(self._indicadores, i, hoy) for i in ORDEN}
            limite = reloj.monotonic() + self.plazo  # un solo plazo para las cuatro
            for institucion, futuro in futuros.items():
                try:
                    restante = max(0.0, limite - reloj.monotonic())
                    indicadores[institucion] = futuro.result(timeout=restante)
                except PlazoVencido:
                    logger.warning("Resumen de plataforma: %s no respondio a tiempo", institucion)
                    indicadores[institucion] = None
                except Exception as error:  # un motor caido no tumba el resumen
                    logger.warning(
                        "Resumen de plataforma: %s no disponible (%s)",
                        institucion,
                        type(error).__name__,
                    )
                    indicadores[institucion] = None
        finally:
            hilos.shutdown(wait=False, cancel_futures=True)
        return ResumenPlataforma(
            tuple(
                ResumenEntidad(
                    institucion=i,
                    administrador=personal[i].administrador,
                    personal_activo=personal[i].por_estado.get(EstadoCuenta.ACTIVA.value, 0),
                    personal_sin_acceso=personal[i].por_estado.get(EstadoCuenta.BLOQUEADA.value, 0)
                    + personal[i].por_estado.get(EstadoCuenta.INACTIVA.value, 0),
                    indicadores=indicadores[i],
                )
                for i in ORDEN
            )
        )
