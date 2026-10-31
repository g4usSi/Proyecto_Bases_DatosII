"""Clinica Odontologica (Firestore): conteos para el resumen de la plataforma.

Usa una consulta de agregacion (count) para no descargar los documentos de pacientes.
"""

from datetime import date

from google.cloud.firestore import Client

from app.domain.plataforma import IndicadoresEntidad


class IndicadoresFirestore:
    def __init__(self, cliente: Client, coleccion_pacientes: str, timeout: float) -> None:
        self.cliente = cliente
        self.coleccion_pacientes = coleccion_pacientes
        self.timeout = timeout

    def conteos(self, hoy: date) -> IndicadoresEntidad:
        resultado = (
            self.cliente.collection(self.coleccion_pacientes)
            .count(alias="total")
            .get(timeout=self.timeout)
        )
        return IndicadoresEntidad(pacientes_registrados=int(resultado[0][0].value))
