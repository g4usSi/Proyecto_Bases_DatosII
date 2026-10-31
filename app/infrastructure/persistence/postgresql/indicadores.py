"""Hospital General (PostgreSQL): conteos para el resumen de la plataforma (sin filas)."""

from datetime import date
from decimal import Decimal

import psycopg

from app.domain.hospital import EstadoCama
from app.domain.plataforma import IndicadoresEntidad
from app.infrastructure.persistence.postgresql.hospital import RepositorioHospitalPostgreSQL


class IndicadoresPostgreSQL:
    def __init__(self, conexion: psycopg.Connection, hospital: RepositorioHospitalPostgreSQL):
        self.conexion = conexion
        self.hospital = hospital

    def conteos(self, hoy: date) -> IndicadoresEntidad:
        (pacientes,) = self.conexion.execute("SELECT count(*) FROM paciente").fetchone()
        resumen = self.hospital.resumen(hoy)
        # Cobros que todavia pueden recibir pagos: abiertos o cerrados con saldo.
        cobros, saldo = self.conexion.execute(
            "SELECT count(*), COALESCE(sum(t.total - t.pagado), 0) FROM ("
            "  SELECT COALESCE((SELECT sum(d.monto) FROM detalle_cobro d "
            "                   WHERE d.id_cobro = c.id_cobro), 0) AS total, "
            "         COALESCE((SELECT sum(g.monto) FROM pago g WHERE g.id_cobro = c.id_cobro "
            "                   AND g.estado = 'Confirmado'), 0) AS pagado "
            "  FROM cobro c WHERE c.estado IN ('Abierto', 'Cerrado')) t"
        ).fetchone()
        return IndicadoresEntidad(
            pacientes_registrados=pacientes,
            camas_ocupadas=resumen.camas_por_estado.get(EstadoCama.OCUPADA.value, 0),
            camas_total=resumen.camas_total,
            emergencias_activas=resumen.emergencias_abiertas,
            cobros_por_cobrar=cobros,
            saldo_por_cobrar=Decimal(saldo).quantize(Decimal("0.01")),
        )
