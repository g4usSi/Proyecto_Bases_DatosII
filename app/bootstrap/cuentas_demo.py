"""Inicializacion idempotente y credenciales visibles para la entrega academica."""

import psycopg
from psycopg.rows import dict_row

from app.core.config import PROJECT_ROOT, Settings
from app.infrastructure.identity.cifrado import CifradorArgon2

MIGRACION_DEMO = PROJECT_ROOT / "database/postgresql/017_cuentas_demo.sql"
CONTRASENA_DEMO = "DemoSalud2026!"
ALCANCES = (
    (None, "Superadmin"),
    ("hospital_general", "Hospital General"),
    ("centro_pediatrico", "Centro Pediatrico"),
    ("laboratorio_clinico", "Laboratorio Clinico"),
    ("clinica_odontologica", "Clinica Odontologica"),
)


def inicializar_cuentas_demo(settings: Settings) -> None:
    if (
        not settings.cuentas_demo
        or settings.environment != "desarrollo"
        or not settings.postgres_dsn
    ):
        return
    # La cuenta limitada de la API ya tiene INSERT/SELECT desde la migracion 012.
    # El SQL contiene su propia transaccion, tambien al ejecutarse mediante psql.
    with psycopg.connect(
        settings.postgres_dsn.get_secret_value(),
        connect_timeout=5,
        autocommit=True,
        row_factory=dict_row,
    ) as conexion:
        conexion.execute(MIGRACION_DEMO.read_text(encoding="utf-8"))
        cuentas = conexion.execute(
            "SELECT DISTINCT ON (establecimiento) establecimiento, correo, password_hash, "
            "activo, bloqueado_hasta > now() AS bloqueada FROM identidad.profesional "
            "WHERE rol IN ('superusuario', 'administrador') AND eliminado_en IS NULL "
            "ORDER BY establecimiento, activo DESC, creado_en, id_profesional"
        ).fetchall()
    por_alcance = {cuenta["establecimiento"]: cuenta for cuenta in cuentas}
    cifrador = CifradorArgon2()
    lineas = ["", "=== Las 5 cuentas de administracion | DEMOSTRACION ==="]
    for alcance, nombre in ALCANCES:
        cuenta = por_alcance.get(alcance)
        if cuenta is None:
            lineas.append(
                f"{nombre}: sin cuenta; revisar si el correo demo ya existe o fue eliminado."
            )
            continue
        clave = (
            CONTRASENA_DEMO
            if cifrador.verificar(CONTRASENA_DEMO, cuenta["password_hash"])
            else "(contrasena existente conservada)"
        )
        estado = ""
        if not cuenta["activo"]:
            estado = " | INACTIVA (estado conservado)"
        elif cuenta["bloqueada"]:
            estado = " | BLOQUEADA (estado conservado)"
        lineas.append(f"{nombre}: usuario={cuenta['correo']} | contrasena={clave}{estado}")
    lineas.extend(
        [
            "Acceso: /app/ | El usuario es el correo electronico.",
            "===================================================",
            "",
        ]
    )
    print("\n".join(lineas), flush=True)
