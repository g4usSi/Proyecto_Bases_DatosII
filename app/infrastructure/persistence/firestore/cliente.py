"""Creacion del cliente de Firestore con el SDK Admin de Firebase.

El SDK Admin se autentica con una cuenta de servicio (IAM) y NO pasa por las
Firestore Security Rules: la autorizacion la hace esta API (JWT + permisos en
PostgreSQL) antes de abrir el adaptador.
"""

from collections.abc import Callable
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore import Client

NOMBRE_APP = "historiales-odontologia"


def crear_cliente_firestore(
    ruta_credenciales: Path, project_id: str | None = None, database: str = "(default)"
) -> tuple[Client, Callable[[], None]]:
    """Devuelve el cliente y la funcion que lo libera al apagar FastAPI.

    Crear el cliente no abre conexiones: un error de red o de permisos aparece en
    la primera lectura/escritura y el adaptador lo convierte en HTTP 503.
    """
    try:
        app = firebase_admin.get_app(NOMBRE_APP)
    except ValueError:
        opciones = {"projectId": project_id} if project_id else None
        app = firebase_admin.initialize_app(
            credentials.Certificate(str(ruta_credenciales)), opciones, name=NOMBRE_APP
        )
    cliente = firestore.client(app=app, database_id=database)

    def cerrar() -> None:
        try:
            cliente.close()
        finally:
            firebase_admin.delete_app(app)

    return cliente, cerrar
