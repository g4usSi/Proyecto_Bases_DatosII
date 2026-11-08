from copy import copy
from logging import LogRecord

from uvicorn.logging import DefaultFormatter


class FormatoInicio(DefaultFormatter):
    def format(self, record: LogRecord) -> str:
        salida = super().format(record)
        if record.name != "uvicorn.error" or not record.msg.startswith("Uvicorn running on %s://"):
            return salida

        # Uvicorn anuncia el puerto asignado incluso con --reload y --port 0.
        esquema, host, puerto = record.args
        host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
        if ":" in host:
            host = f"[{host}]"

        enlace = copy(record)
        enlace.msg = f"Aplicación web: {esquema}://{host}:{puerto}/app/"
        enlace.args = ()
        enlace.__dict__.pop("color_message", None)
        return f"{salida}\n{super().format(enlace)}"
