"""Adendas, correccion de datos y alergias nuevas, probadas con dobles (sin motores)."""

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.consulta import Diagnostico, NuevaConsulta
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.paciente import Alergia, Paciente
from app.main import create_app
from tests.doubles import AutenticadorDoble, HistorialDoble, UnidadTrabajoDoble

AUTH = {"Authorization": "Bearer valido"}
TODOS = frozenset(
    {
        "pacientes:leer",
        "pacientes:registrar",
        "historiales:leer",
        "consultas:registrar",
        "historiales:archivar",
    }
)


def preparar(settings: Settings, permisos=TODOS, archivado=False):
    historial = HistorialDoble()
    unidad = UnidadTrabajoDoble(
        {"1": Paciente("1", "Ana", "Lopez", alergias=(Alergia("Latex"),), archivado=archivado)},
        historial,
    )
    historial.registrar_consulta("1", "prof-1", NuevaConsulta("Dolor", "Primera"))
    usuario = UsuarioAutenticado("prof-1", Institucion.CLINICA_ODONTOLOGICA, permisos)
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"valido": usuario}),
        unidades_trabajo={Institucion.CLINICA_ODONTOLOGICA: lambda: unidad},
    )
    return TestClient(create_app(settings, contenedor)), unidad


def test_adenda_agrega_y_rotula_con_quien_y_cuando(settings: Settings) -> None:
    client, unidad = preparar(settings)
    with client:
        respuesta = client.post(
            "/api/v1/pacientes/1/consultas/1/adenda",
            json={"nota": "Aclaracion", "diagnosticos": [{"descripcion": "Gingivitis"}]},
            headers=AUTH,
        )
        leida = client.get("/api/v1/pacientes/1/consultas/1", headers=AUTH)
    assert respuesta.status_code == 200 and leida.json() == respuesta.json()
    datos = respuesta.json()
    assert datos["diagnosticos"][0]["descripcion"] == "Gingivitis"
    assert (
        datos["notas"].startswith("Primera\n\n[Adenda ") and "profesional prof-1" in datos["notas"]
    )
    assert unidad.confirmaciones == 1


def test_adenda_vacia_inexistente_o_archivada(settings: Settings) -> None:
    client, unidad = preparar(settings)
    with client:
        assert (
            client.post("/api/v1/pacientes/1/consultas/1/adenda", json={}, headers=AUTH).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/pacientes/1/consultas/99/adenda", json={"nota": "x"}, headers=AUTH
            ).status_code
            == 404
        )
        assert client.get("/api/v1/pacientes/1/consultas/99", headers=AUTH).status_code == 404
        assert client.get("/api/v1/pacientes/9/consultas/1", headers=AUTH).status_code == 404
    assert unidad.confirmaciones == 0
    archivado, _ = preparar(settings, archivado=True)
    with archivado:
        respuesta = archivado.post(
            "/api/v1/pacientes/1/consultas/1/adenda", json={"nota": "x"}, headers=AUTH
        )
    assert respuesta.status_code == 409


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo", "permiso"),
    [
        ("patch", "/api/v1/pacientes/1", {"nombres": "Nuevo"}, "pacientes:registrar"),
        (
            "post",
            "/api/v1/pacientes/1/alergias",
            {"alergias": [{"sustancia": "Polen"}]},
            "pacientes:registrar",
        ),
        ("get", "/api/v1/pacientes/1/consultas/1", None, "historiales:leer"),
        (
            "post",
            "/api/v1/pacientes/1/consultas/1/adenda",
            {"nota": "x"},
            "consultas:registrar",
        ),
    ],
)
def test_las_rutas_nuevas_exigen_su_permiso(settings, metodo, ruta, cuerpo, permiso) -> None:
    client, unidad = preparar(settings, TODOS - {permiso})
    with client:
        assert client.request(metodo, ruta, json=cuerpo, headers=AUTH).status_code == 403
    assert unidad.confirmaciones == 0


def test_corregir_paciente_y_alergias(settings: Settings) -> None:
    client, unidad = preparar(settings)
    with client:
        assert client.patch("/api/v1/pacientes/1", json={}, headers=AUTH).status_code == 422
        assert (
            client.patch(
                "/api/v1/pacientes/1", json={"fecha_nacimiento": "2999-01-01"}, headers=AUTH
            ).status_code
            == 422
        )
        assert (
            client.patch("/api/v1/pacientes/1", json={"id_paciente": "2"}, headers=AUTH).status_code
            == 422
        )
        corregido = client.patch(
            "/api/v1/pacientes/1",
            json={"nombres": "Ana Maria", "contacto": {"telefono": "123"}},
            headers=AUTH,
        )
        repetida = client.post(
            "/api/v1/pacientes/1/alergias",
            json={"alergias": [{"sustancia": "LATEX"}]},
            headers=AUTH,
        )
        doble = client.post(
            "/api/v1/pacientes/1/alergias",
            json={"alergias": [{"sustancia": "Polen"}, {"sustancia": "polen"}]},
            headers=AUTH,
        )
        nueva = client.post(
            "/api/v1/pacientes/1/alergias",
            json={"alergias": [{"sustancia": "Polen"}]},
            headers=AUTH,
        )
        inexistente = client.patch("/api/v1/pacientes/9", json={"nombres": "X"}, headers=AUTH)
    assert corregido.status_code == 200 and corregido.json()["nombres"] == "Ana Maria"
    assert corregido.json()["contacto"]["telefono"] == "123"
    assert repetida.status_code == 422 and doble.status_code == 422
    assert [a["sustancia"] for a in nueva.json()["alergias"]] == ["Latex", "Polen"]
    assert inexistente.status_code == 404
    assert unidad.confirmaciones == 2


def test_historial_con_diagnosticos_previos_no_se_pierde_al_agregar(settings: Settings) -> None:
    client, unidad = preparar(settings)
    unidad.historial.consultas[0] = unidad.historial.consultas[0].__class__(
        "1",
        "1",
        "prof-1",
        unidad.historial.consultas[0].fecha_hora,
        "Dolor",
        None,
        (Diagnostico("Caries"),),
    )
    with client:
        respuesta = client.post(
            "/api/v1/pacientes/1/consultas/1/adenda",
            json={"diagnosticos": [{"descripcion": "Pulpitis"}]},
            headers=AUTH,
        )
    assert [d["descripcion"] for d in respuesta.json()["diagnosticos"]] == ["Caries", "Pulpitis"]
    assert respuesta.json()["notas"].startswith("[Adenda ")


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo"),
    [
        ("get", "/api/v1/pacientes/1/crecimiento", None),
        ("post", "/api/v1/pacientes/1/crecimiento", {"peso_kg": 5}),
        ("get", "/api/v1/vacunas", None),
        ("get", "/api/v1/pacientes/1/vacunacion", None),
        ("post", "/api/v1/pacientes/1/vacunacion", {"id_vacuna": "1"}),
        ("post", "/api/v1/pacientes/1/vacunacion/esquema-recomendado", None),
        ("post", "/api/v1/pacientes/1/vacunacion/1/aplicar", {}),
        ("post", "/api/v1/pacientes/1/vacunacion/1/cancelar", None),
    ],
)
def test_crecimiento_y_vacunacion_son_solo_del_centro_pediatrico(
    settings, metodo, ruta, cuerpo
) -> None:
    client, unidad = preparar(settings)
    with client:
        respuesta = client.request(metodo, ruta, json=cuerpo, headers=AUTH)
    assert respuesta.status_code == 501
    assert "Centro Pediatrico" in respuesta.json()["detail"]
    assert unidad.confirmaciones == 0


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo", "permiso"),
    [
        ("get", "/api/v1/pacientes/1/crecimiento", None, "historiales:leer"),
        ("post", "/api/v1/pacientes/1/crecimiento", {"peso_kg": 5}, "consultas:registrar"),
        ("get", "/api/v1/vacunas", None, "historiales:leer"),
        ("post", "/api/v1/pacientes/1/vacunacion", {"id_vacuna": "1"}, "consultas:registrar"),
        (
            "post",
            "/api/v1/pacientes/1/vacunacion/1/aplicar",
            {},
            "consultas:registrar",
        ),
    ],
)
def test_rutas_pediatricas_exigen_su_permiso(settings, metodo, ruta, cuerpo, permiso) -> None:
    client, _ = preparar(settings, TODOS - {permiso})
    with client:
        assert client.request(metodo, ruta, json=cuerpo, headers=AUTH).status_code == 403


def test_calculos_de_edad_en_meses() -> None:
    from datetime import date

    from app.domain.pediatria import meses_cumplidos, sumar_meses

    assert meses_cumplidos(date(2024, 1, 31), date(2024, 2, 29)) == 0
    assert meses_cumplidos(date(2024, 1, 15), date(2024, 3, 15)) == 2
    assert meses_cumplidos(date(2024, 1, 15), date(2023, 1, 1)) == 0  # nunca negativa
    assert sumar_meses(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert sumar_meses(date(2024, 11, 30), 3) == date(2025, 2, 28)
    assert sumar_meses(date(2024, 5, 10), 24) == date(2026, 5, 10)


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo"),
    [
        ("get", "/api/v1/laboratorio/pruebas", None),
        ("post", "/api/v1/pacientes/1/ordenes", {"id_consulta": "1", "pruebas": ["A"]}),
        ("get", "/api/v1/pacientes/1/ordenes", None),
        ("get", "/api/v1/pacientes/1/ordenes/1", None),
        ("post", "/api/v1/pacientes/1/ordenes/1/muestras", {"tipo": "sangre"}),
        (
            "put",
            "/api/v1/pacientes/1/ordenes/1/pruebas/A/resultados",
            {"valores": [{"codigo_parametro": "X", "valor": 1}]},
        ),
        ("post", "/api/v1/pacientes/1/ordenes/1/validar", None),
        ("post", "/api/v1/pacientes/1/ordenes/1/cancelar", {"motivo": "x"}),
    ],
)
def test_ordenes_de_laboratorio_son_solo_del_laboratorio_clinico(
    settings, metodo, ruta, cuerpo
) -> None:
    client, unidad = preparar(settings)
    permisos = TODOS | {"laboratorio:resultados", "laboratorio:validar"}
    client, unidad = preparar(settings, permisos)
    with client:
        respuesta = client.request(metodo, ruta, json=cuerpo, headers=AUTH)
    assert respuesta.status_code == 501, respuesta.text
    assert "Laboratorio Clinico" in respuesta.json()["detail"]
    assert unidad.confirmaciones == 0


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo", "falta"),
    [
        (
            "get",
            "/api/v1/laboratorio/pruebas",
            None,
            {"historiales:leer", "laboratorio:resultados"},
        ),
        (
            "get",
            "/api/v1/pacientes/1/ordenes",
            None,
            {"historiales:leer", "laboratorio:resultados"},
        ),
        (
            "post",
            "/api/v1/pacientes/1/ordenes",
            {"id_consulta": "1", "pruebas": ["A"]},
            {"consultas:registrar"},
        ),
        (
            "post",
            "/api/v1/pacientes/1/ordenes/1/muestras",
            {"tipo": "x"},
            {"laboratorio:resultados"},
        ),
        (
            "put",
            "/api/v1/pacientes/1/ordenes/1/pruebas/A/resultados",
            {"valores": [{"codigo_parametro": "X", "valor": 1}]},
            {"laboratorio:resultados"},
        ),
        ("post", "/api/v1/pacientes/1/ordenes/1/validar", None, {"laboratorio:validar"}),
        (
            "post",
            "/api/v1/pacientes/1/ordenes/1/cancelar",
            {"motivo": "x"},
            {"consultas:registrar"},
        ),
    ],
)
def test_ordenes_exigen_el_permiso_correcto(settings, metodo, ruta, cuerpo, falta) -> None:
    con = TODOS | {"laboratorio:resultados", "laboratorio:validar"}
    client, _ = preparar(settings, con - falta)
    with client:
        assert client.request(metodo, ruta, json=cuerpo, headers=AUTH).status_code == 403


def test_leer_ordenes_basta_con_historiales_leer_o_con_resultados(settings) -> None:
    for permiso in ("historiales:leer", "laboratorio:resultados"):
        client, _ = preparar(settings, frozenset({"pacientes:leer", permiso}))
        with client:
            respuesta = client.get("/api/v1/pacientes/1/ordenes", headers=AUTH)
        assert respuesta.status_code == 501  # llego al motor: el permiso alcanzo


def test_permisos_del_laboratorista_y_vedados_a_la_secretaria() -> None:
    from app.domain import permisos

    assert permisos.LABORATORIO_RESULTADOS in permisos.PERMISOS_POR_ROL["laboratorista"]
    assert permisos.LABORATORIO_VALIDAR in permisos.PERMISOS_VEDADOS_SECRETARIA
    assert permisos.LABORATORIO_RESULTADOS in permisos.PERMISOS_VEDADOS_SECRETARIA
    assert not permisos.PERMISOS_POR_ROL["secretaria"] & permisos.PERMISOS_VEDADOS_SECRETARIA
