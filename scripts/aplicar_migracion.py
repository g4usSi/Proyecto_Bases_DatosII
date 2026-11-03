"""Aplica archivos SQL/JS pendientes en Docker y asegura las cinco cuentas demo.

Ejemplo: python -m scripts.aplicar_migracion database/postgresql/016_frontend_hospital.sql
Los archivos se ejecutan en el orden indicado. No repite ni adivina migraciones anteriores.
"""

import argparse
import subprocess
from pathlib import Path

from app.bootstrap.cuentas_demo import MIGRACION_DEMO, inicializar_cuentas_demo
from app.core.config import PROJECT_ROOT, Settings

POSTGRES = [
    "postgres",
    "psql",
    "-v",
    "ON_ERROR_STOP=1",
    "-U",
    "historiales_admin",
    "-d",
    "hospital_general",
]
MYSQL = [
    "mysql",
    "sh",
    "-c",
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot '
    "--default-character-set=utf8mb4 hospital_pediatrico",
]
MONGO = [
    "mongo",
    "sh",
    "-c",
    'exec mongosh --quiet -u historiales_admin -p "$MONGO_INITDB_ROOT_PASSWORD" '
    "--authenticationDatabase admin --file /dev/stdin",
]


def comando_para(ruta: Path) -> list[str]:
    if ruta.parent == PROJECT_ROOT / "database/postgresql" and ruta.suffix == ".sql":
        return POSTGRES
    if ruta.parent == PROJECT_ROOT / "database/mysql" and ruta.suffix == ".sql":
        return MYSQL
    if ruta == PROJECT_ROOT / "laboratorio_clinico_mongo.js":
        return MONGO
    raise ValueError(f"Migracion fuera de los directorios del proyecto: {ruta}")


def ejecutar(ruta: Path, comando: list[str]) -> None:
    print(f"Aplicando {ruta.relative_to(PROJECT_ROOT)}...", flush=True)
    subprocess.run(
        ["docker", "compose", "exec", "-T", *comando],
        input=ruta.read_bytes(),
        cwd=PROJECT_ROOT,
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archivos", nargs="+", type=Path)
    args = parser.parse_args()
    try:
        migraciones = [(ruta.resolve(), comando_para(ruta.resolve())) for ruta in args.archivos]
        for ruta, _ in migraciones:
            if not ruta.is_file():
                raise ValueError(f"No existe el archivo: {ruta}")
        for ruta, comando in migraciones:
            ejecutar(ruta, comando)
        # Mismo seed para cualquier motor. Identidad debe tener ya las migraciones 001-015.
        ejecutar(MIGRACION_DEMO, POSTGRES)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"No se completo la migracion: {error}\n")
    inicializar_cuentas_demo(Settings())
    print("Migraciones aplicadas y cuentas de demostracion verificadas.")


if __name__ == "__main__":
    main()
