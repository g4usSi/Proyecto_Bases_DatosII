"""Centro Pediatrico (MySQL): conteos para el resumen de la plataforma (sin filas)."""

from datetime import date
from decimal import Decimal

import pymysql

from app.domain.plataforma import IndicadoresEntidad


class IndicadoresMySQL:
    def __init__(self, conexion: pymysql.Connection) -> None:
        self.conexion = conexion

    def conteos(self, hoy: date) -> IndicadoresEntidad:
        with self.conexion.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM paciente")
            (pacientes,) = cursor.fetchone()
            # Por cobrar: no anuladas y con saldo (o todavia sin cargos).
            cursor.execute(
                "SELECT count(*), COALESCE(sum(total_facturado - total_pagado), 0) "
                "FROM facturacion WHERE anulada_en IS NULL "
                "AND NOT (total_facturado > 0 AND total_pagado = total_facturado)"
            )
            facturas, saldo = cursor.fetchone()
        return IndicadoresEntidad(
            pacientes_registrados=pacientes,
            cobros_por_cobrar=facturas,
            saldo_por_cobrar=Decimal(saldo).quantize(Decimal("0.01")),
        )
