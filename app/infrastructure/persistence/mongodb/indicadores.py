"""Laboratorio Clinico (MongoDB): conteos para el resumen de la plataforma (sin filas)."""

from datetime import date

from pymongo.database import Database

from app.domain.plataforma import IndicadoresEntidad


class IndicadoresMongo:
    def __init__(self, database: Database) -> None:
        self.database = database

    def conteos(self, hoy: date) -> IndicadoresEntidad:
        # Importacion tardia: unidad.py importa este modulo.
        from app.infrastructure.persistence.mongodb.unidad import ABIERTAS_BD as abiertas

        return IndicadoresEntidad(
            pacientes_registrados=self.database.pacientes.count_documents({}),
            ordenes_abiertas=self.database.ordenes_laboratorio.count_documents(
                {"estado": {"$in": abiertas}}
            ),
        )
