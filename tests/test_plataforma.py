"""Resumen de plataforma con dobles: solo conteos y respuesta parcial si un motor falla."""

import time
from dataclasses import replace

from fastapi.testclient import TestClient

from app.application.errores import IntegracionNoConfigurada
from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.paciente import Paciente
from app.main import create_app
from tests.doubles import (
    AutenticadorDoble,
    CifradorDoble,
    DirectorioAdministrableDoble,
    UnidadTrabajoDoble,
)

SUPER = UsuarioAutenticado("su", None, frozenset({"plataforma:administrar", "pagos:ver"}))
ADMIN = UsuarioAutenticado(
    "adm", Institucion.HOSPITAL_GENERAL, frozenset({"profesionales:administrar"})
)


def caido():
    raise IntegracionNoConfigurada("La base del laboratorio no esta disponible.")


def test_resumen_solo_conteos_y_motor_caido_en_null(settings: Settings) -> None:
    pacientes = {"1": Paciente("1", "Ana", "Lopez"), "2": Paciente("2", "Luis", "Paz")}
    unidades = {
        Institucion.HOSPITAL_GENERAL: lambda: UnidadTrabajoDoble(pacientes),
        Institucion.CENTRO_PEDIATRICO: lambda: UnidadTrabajoDoble({}),
        Institucion.LABORATORIO_CLINICO: caido,
        # La clinica odontologica no esta configurada: tambien sale como null.
    }
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"su": SUPER, "adm": ADMIN}),
        administracion=DirectorioAdministrableDoble(),
        cifrador=CifradorDoble(),
        unidades_trabajo=unidades,
    )
    with TestClient(create_app(settings, contenedor)) as client:
        respuesta = client.get("/api/v1/plataforma/resumen", headers={"Authorization": "Bearer su"})
        admin = client.get("/api/v1/plataforma/resumen", headers={"Authorization": "Bearer adm"})
    assert respuesta.status_code == 200, respuesta.text
    entidades = {e["institucion"]: e for e in respuesta.json()["entidades"]}
    assert list(entidades) == [
        "hospital_general",
        "centro_pediatrico",
        "laboratorio_clinico",
        "clinica_odontologica",
    ]
    hospital = entidades["hospital_general"]["indicadores"]
    assert hospital["pacientes_registrados"] == 2 and hospital["citas_hoy"] == 0
    assert entidades["laboratorio_clinico"]["indicadores"] is None
    assert entidades["clinica_odontologica"]["indicadores"] is None
    # Nunca nombres ni ids de pacientes.
    assert "Ana" not in respuesta.text and "Lopez" not in respuesta.text
    assert admin.status_code == 403


def test_un_motor_lento_no_bloquea_el_resumen(settings: Settings) -> None:
    from app.application.use_cases.plataforma import ResumenDePlataforma

    class UnidadLenta(UnidadTrabajoDoble):
        def __enter__(self):
            time.sleep(2)
            return self

    def abrir(institucion):
        if institucion == Institucion.LABORATORIO_CLINICO:
            return UnidadLenta({})
        return UnidadTrabajoDoble({})

    from zoneinfo import ZoneInfo

    inicio = time.monotonic()
    resumen = ResumenDePlataforma(
        DirectorioAdministrableDoble(), abrir, ZoneInfo("America/Guatemala"), plazo_segundos=0.5
    ).ejecutar()
    assert time.monotonic() - inicio < 1.5
    por_entidad = {e.institucion: e for e in resumen.entidades}
    assert por_entidad[Institucion.LABORATORIO_CLINICO].indicadores is None
    assert por_entidad[Institucion.HOSPITAL_GENERAL].indicadores is not None
    assert replace(por_entidad[Institucion.HOSPITAL_GENERAL]).personal_activo == 0
