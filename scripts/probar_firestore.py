"""Comprueba la conexion con Cloud Firestore usando la configuracion de .env.

Uso, desde la raiz del proyecto y con el entorno virtual activo:
    python -m scripts.probar_firestore

Escribe un documento temporal en la coleccion `_diagnostico`, lo lee y lo borra.
No toca la coleccion `pacientes`.
"""

import sys
from uuid import uuid4

from google.api_core.exceptions import GoogleAPIError, NotFound, PermissionDenied
from google.auth.exceptions import GoogleAuthError
from google.cloud import firestore

from app.core.config import Settings
from app.infrastructure.persistence.firestore.cliente import crear_cliente_firestore


def main() -> int:
    settings = Settings()
    ruta = settings.firestore_credentials
    if ruta is None:
        print("Falta HISTORIALES_FIRESTORE_CREDENTIALS en .env.")
        print("Ejecuta: python -m scripts.configurar_desarrollo")
        return 1
    if not ruta.is_file():
        print(f"No existe la clave en: {ruta}")
        print("Descargala en Firebase > Configuracion del proyecto > Cuentas de servicio.")
        return 1
    cliente, cerrar = crear_cliente_firestore(
        ruta, settings.firestore_project_id, settings.firestore_database
    )
    print(f"Proyecto: {cliente.project} | Base de datos: {settings.firestore_database}")
    documento = cliente.collection("_diagnostico").document(f"prueba-{uuid4().hex}")
    try:
        documento.set({"creado_en": firestore.SERVER_TIMESTAMP, "origen": "probar_firestore"})
        leido = documento.get(timeout=15)
        documento.delete()
        print(f"OK: escritura, lectura y borrado funcionan (existia={leido.exists}).")
        return 0
    except NotFound as error:
        print("La base de datos no existe. Crea Firestore en la consola o revisa")
        print(f"HISTORIALES_FIRESTORE_DATABASE. Detalle: {error.message}")
    except PermissionDenied as error:
        print("La cuenta de servicio no tiene permisos o la API de Firestore esta apagada.")
        print(f"Detalle: {error.message}")
    except (GoogleAPIError, GoogleAuthError) as error:
        print(f"No se pudo conectar con Firestore: {error}")
    finally:
        cerrar()
    return 1


if __name__ == "__main__":
    sys.exit(main())
