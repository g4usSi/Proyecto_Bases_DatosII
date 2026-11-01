"""Interfaz web: archivos estaticos servidos por la misma API, sin compilacion ni Node."""

import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

DIRECTORIO = Path(__file__).resolve().parent

# En Windows, mimetypes lee el registro del sistema: si .js figura como text/plain, el
# navegador rechaza los modulos ES y la pantalla queda en blanco.
TIPOS = {
    ".js": "text/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
}


def montar_frontend(app: FastAPI) -> None:
    for extension, tipo in TIPOS.items():
        mimetypes.add_type(tipo, extension)
    app.mount("/app", StaticFiles(directory=DIRECTORIO, html=True), name="frontend")
