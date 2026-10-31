"""Resumen de plataforma: cuatro lecturas independientes y respuesta parcial."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.application.errores import IntegracionNoConfigurada, OperacionPendiente
from app.application.ports.administracion import DirectorioAdministrable
from app.application.ports.unidad_trabajo import UnidadDeTrabajo
from app.domain.institucion import Institucion

logger = logging.getLogger(__name__)


class ResumenDePlataforma:
    def __init__(
        self,
        directorio: DirectorioAdministrable | None,
        abrir: Callable[[Institucion], UnidadDeTrabajo],
        zona: ZoneInfo,
    ):
        self.directorio = directorio
        self.abrir = abrir
        self.zona = zona

    def _entidad(self, institucion, desde, hasta):
        try:
            personal = self.directorio.resumen(institucion)
            with self.abrir(institucion) as unidad:
                conteos = unidad.resumen_operativo(desde, hasta)
            return {
                "administrador_activo": personal.administrador_activo,
                "personal_activo": personal.por_estado.get("activa", 0),
                "personal_sin_acceso": sum(
                    n for estado, n in personal.por_estado.items() if estado != "activa"
                ),
                **conteos,
            }
        except (IntegracionNoConfigurada, OperacionPendiente) as error:
            # El resumen es parcial. Los errores se registran sin credenciales ni pacientes.
            logger.warning(
                "Resumen no disponible para %s (%s)", institucion.value, type(error).__name__
            )
            return None

    def ejecutar(self):
        if self.directorio is None:
            raise IntegracionNoConfigurada("La identidad central no esta configurada.")
        hoy = datetime.now(self.zona).date()
        desde = datetime.combine(hoy, time.min, self.zona)
        hasta = datetime.combine(hoy + timedelta(days=1), time.min, self.zona)
        # Cada adaptador limita sus operaciones de red; no hay un motor global mutable.
        ejecutor = ThreadPoolExecutor(max_workers=4)
        try:
            resultados = {i: ejecutor.submit(self._entidad, i, desde, hasta) for i in Institucion}
            terminados, _ = wait(resultados.values(), timeout=15)
            return {
                i.value: resultado.result() if resultado in terminados else None
                for i, resultado in resultados.items()
            }
        finally:
            ejecutor.shutdown(wait=False, cancel_futures=True)
