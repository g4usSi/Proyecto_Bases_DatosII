"""Rutas del Hospital General con dobles: 501 fuera del hospital, validaciones y permisos."""

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.consulta import Receta
from app.domain.errores import DatosInvalidos
from app.domain.hospital import NuevaOrdenMedica, TipoOrdenMedica
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.paciente import Paciente
from app.main import create_app
from tests.doubles import AutenticadorDoble, UnidadTrabajoDoble

H = {"Authorization": "Bearer t"}
TODOS = frozenset({"pacientes:leer", "historiales:leer", "consultas:registrar", "camas:gestionar"})


def cliente(settings: Settings, permisos=TODOS) -> TestClient:
    usuario = UsuarioAutenticado("u1", Institucion.LABORATORIO_CLINICO, permisos)
    unidad = UnidadTrabajoDoble({"1": Paciente("1", "Ana", "Lopez")})
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"t": usuario}),
        unidades_trabajo={Institucion.LABORATORIO_CLINICO: lambda: unidad},
    )
    return TestClient(create_app(settings, contenedor))


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo"),
    [
        ("get", "/api/v1/camas", None),
        ("get", "/api/v1/ingresos", None),
        ("get", "/api/v1/hospital/resumen", None),
        ("get", "/api/v1/pacientes/1/ingresos", None),
        (
            "post",
            "/api/v1/pacientes/1/ingresos",
            {"id_cama": 1, "tipo": "emergencia", "motivo": "X"},
        ),
        ("post", "/api/v1/camas/1/estado", {"estado": "limpieza"}),
    ],
)
def test_fuera_del_hospital_responde_501(settings: Settings, metodo, ruta, cuerpo) -> None:
    with cliente(settings) as client:
        respuesta = getattr(client, metodo)(ruta, headers=H, **({"json": cuerpo} if cuerpo else {}))
    assert respuesta.status_code == 501 and "Hospital General" in respuesta.text


def test_validaciones_antes_de_tocar_la_base(settings: Settings) -> None:
    with cliente(settings) as client:
        ocupada = client.post("/api/v1/camas/1/estado", json={"estado": "ocupada"}, headers=H)
        tipo = client.post(
            "/api/v1/pacientes/1/ingresos",
            json={"id_cama": 1, "tipo": "urgente", "motivo": "X"},
            headers=H,
        )
        examen = client.post(
            "/api/v1/pacientes/1/ingresos/5/ordenes", json={"tipo": "examen"}, headers=H
        )
    assert ocupada.status_code == 422 and tipo.status_code == 422 and examen.status_code == 422


def test_cambiar_cama_exige_camas_gestionar(settings: Settings) -> None:
    with cliente(settings, frozenset({"pacientes:leer"})) as client:
        respuesta = client.post("/api/v1/camas/1/estado", json={"estado": "limpieza"}, headers=H)
    assert respuesta.status_code == 403


def test_reglas_de_la_orden_medica() -> None:
    receta = Receta("Aspirina", "100 mg", "c/24h")
    NuevaOrdenMedica(TipoOrdenMedica.MEDICAMENTO, recetas=(receta,)).validar()
    NuevaOrdenMedica(TipoOrdenMedica.INTERCONSULTA, "Cardiologia").validar()
    for invalida in (
        NuevaOrdenMedica(TipoOrdenMedica.MEDICAMENTO),
        NuevaOrdenMedica(TipoOrdenMedica.EXAMEN, "  "),
        NuevaOrdenMedica(TipoOrdenMedica.EXAMEN, "Rayos X", (receta,)),
    ):
        with pytest.raises(DatosInvalidos):
            invalida.validar()
