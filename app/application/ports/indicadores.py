from datetime import date
from typing import Protocol

from app.domain.plataforma import IndicadoresEntidad


class RepositorioIndicadores(Protocol):
    """Conteos de UNA entidad para el resumen de plataforma. Solo agregados: nunca filas
    de pacientes. Las citas las cuenta el caso de uso con la agenda comun."""

    def conteos(self, hoy: date) -> IndicadoresEntidad: ...
