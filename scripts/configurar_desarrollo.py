"""Agregar configuracion local faltante sin sobrescribir valores del usuario."""

import secrets
from pathlib import Path
from urllib.parse import quote

from dotenv import dotenv_values

RAIZ = Path(__file__).resolve().parents[1]


def main() -> None:
    archivo = RAIZ / ".env"
    valores = dict(dotenv_values(archivo)) if archivo.exists() else {}
    nuevos: dict[str, str] = {}

    def asegurar(clave: str, valor: str) -> str:
        if valores.get(clave):
            return str(valores[clave])
        nuevos[clave] = valor
        valores[clave] = valor
        return valor

    pg = asegurar("POSTGRES_PASSWORD", secrets.token_urlsafe(32))
    pg_app = asegurar("POSTGRES_APP_PASSWORD", secrets.token_urlsafe(32))
    asegurar("MYSQL_ROOT_PASSWORD", secrets.token_urlsafe(32))
    mysql = asegurar("MYSQL_PASSWORD", secrets.token_urlsafe(32))
    asegurar("MONGO_ROOT_PASSWORD", secrets.token_urlsafe(32))
    mongo = asegurar("MONGO_APP_PASSWORD", secrets.token_urlsafe(32))
    asegurar("HISTORIALES_JWT_SECRET", secrets.token_urlsafe(48))
    pg_port = asegurar("POSTGRES_PORT", "5434")
    mysql_port = asegurar("MYSQL_PORT", "3307")
    mongo_port = asegurar("MONGO_PORT", "27018")
    asegurar(
        "HISTORIALES_POSTGRES_DSN",
        f"postgresql://historiales_app:{quote(pg_app, safe='')}"
        f"@127.0.0.1:{pg_port}/hospital_general",
    )
    asegurar(
        "HISTORIALES_POSTGRES_ADMIN_DSN",
        f"postgresql://historiales_admin:{quote(pg, safe='')}@127.0.0.1:{pg_port}/hospital_general",
    )
    asegurar("HISTORIALES_MYSQL_HOST", "127.0.0.1")
    asegurar("HISTORIALES_MYSQL_PORT", mysql_port)
    asegurar("HISTORIALES_MYSQL_USER", "historiales_app")
    asegurar("HISTORIALES_MYSQL_PASSWORD", mysql)
    asegurar(
        "HISTORIALES_MONGODB_URI",
        f"mongodb://historiales_app:{quote(mongo, safe='')}@127.0.0.1:{mongo_port}"
        "/laboratorio_clinico?authSource=laboratorio_clinico",
    )
    if nuevos:
        with archivo.open("a", encoding="utf-8") as salida:
            salida.write("\n# Configuracion local de motores e identidad (no subir a Git).\n")
            for clave, valor in nuevos.items():
                salida.write(f'{clave}="{valor}"\n')
    print(
        f"Configuracion lista: {len(nuevos)} variables agregadas. Secretos guardados solo en .env."
    )


if __name__ == "__main__":
    main()
