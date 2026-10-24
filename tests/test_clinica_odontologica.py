"""Rol secretaria, citas y odontograma, con dobles (sin Firestore)."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain import permisos
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.odontograma import EstadoDental
from app.domain.paciente import Alergia, Paciente
from app.domain.profesional import ProfesionalLocal
from app.main import create_app
from tests.doubles import AutenticadorDoble, UnidadTrabajoDoble

SECRETARIA = UsuarioAutenticado(
    "sec-1", Institucion.CLINICA_ODONTOLOGICA, permisos.PERMISOS_POR_ROL["secretaria"]
)
ODONTOLOGO = UsuarioAutenticado(
    "odo-1",
    Institucion.CLINICA_ODONTOLOGICA,
    frozenset(
        {
            permisos.PACIENTES_LEER,
            permisos.HISTORIALES_LEER,
            permisos.CONSULTAS_REGISTRAR,
            permisos.CITAS_LEER,
            permisos.CITAS_GESTIONAR,
        }
    ),
)
SEC = {"Authorization": "Bearer secretaria"}
ODO = {"Authorization": "Bearer odontologo"}


def preparar(settings: Settings) -> tuple[TestClient, UnidadTrabajoDoble]:
    unidad = UnidadTrabajoDoble(
        {"p1": Paciente("p1", "Luis", "Perez", alergias=(Alergia("Penicilina"),))},
        profesionales={
            "odo-1": ProfesionalLocal("odo-1", "Ana", "Diaz", "odontologo"),
            "sec-1": ProfesionalLocal("sec-1", "Eva", "Ruiz", "secretaria"),
            "baja": ProfesionalLocal("baja", "X", "Y", "odontologo", activo=False),
        },
    )
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"secretaria": SECRETARIA, "odontologo": ODONTOLOGO}),
        unidades_trabajo={Institucion.CLINICA_ODONTOLOGICA: lambda: unidad},
    )
    return TestClient(create_app(settings, contenedor)), unidad


def manana(hora: int, minuto: int = 0) -> str:
    dia = datetime.now(UTC) + timedelta(days=1)
    return dia.replace(hour=hora, minute=minuto, second=0, microsecond=0).isoformat()


def cita(inicio: str, profesional: str = "odo-1", duracion: int = 30) -> dict:
    return {
        "id_paciente": "p1",
        "id_profesional": profesional,
        "inicio": inicio,
        "duracion_minutos": duracion,
        "motivo": "Limpieza",
    }


def test_secretaria_registra_pero_no_ve_informacion_clinica(settings: Settings) -> None:
    client, _ = preparar(settings)
    with client:
        alta = client.post(
            "/api/v1/pacientes",
            json={
                "nombres": "Rosa",
                "apellidos": "Gomez",
                "contacto": {"telefono": "5555-0000"},
                "alergias": [{"sustancia": "Latex"}],
            },
            headers=SEC,
        )
        lectura_sec = client.get("/api/v1/pacientes/p1", headers=SEC)
        lectura_odo = client.get("/api/v1/pacientes/p1", headers=ODO)
        historial = client.get("/api/v1/pacientes/p1/historial", headers=SEC)
        consulta = client.post("/api/v1/pacientes/p1/consultas", json={"motivo": "x"}, headers=SEC)
        odontograma = client.get("/api/v1/pacientes/p1/odontograma", headers=SEC)
    assert alta.status_code == 201
    assert alta.json()["contacto"]["telefono"] == "5555-0000"
    assert alta.json()["alergias"] is None  # la secretaria no las ve, aunque las registre
    assert lectura_sec.json()["alergias"] is None
    assert lectura_odo.json()["alergias"] == [
        {"sustancia": "Penicilina", "reaccion": None, "severidad": None}
    ]
    assert historial.status_code == 403
    assert consulta.status_code == 403
    assert odontograma.status_code == 403


def test_secretaria_agenda_y_no_se_cruzan_horarios(settings: Settings) -> None:
    client, _ = preparar(settings)
    with client:
        primera = client.post("/api/v1/citas", json=cita(manana(15)), headers=SEC)
        cruzada = client.post("/api/v1/citas", json=cita(manana(15, 15)), headers=SEC)
        contigua = client.post("/api/v1/citas", json=cita(manana(15, 30)), headers=SEC)
        agenda = client.get(
            "/api/v1/citas",
            params={"desde": manana(0), "hasta": manana(23), "id_profesional": "odo-1"},
            headers=SEC,
        )
        del_paciente = client.get("/api/v1/pacientes/p1/citas", headers=SEC)
    assert primera.status_code == 201
    assert primera.json()["nombre_paciente"] == "Luis Perez"
    assert primera.json()["creada_por"] == "sec-1"
    assert cruzada.status_code == 409
    assert contigua.status_code == 201
    assert [c["id_cita"] for c in agenda.json()] == ["1", "2"]
    assert len(del_paciente.json()) == 2


def test_cita_rechaza_pasado_secretaria_como_profesional_y_profesional_inactivo(
    settings: Settings,
) -> None:
    client, _ = preparar(settings)
    ayer = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    with client:
        pasada = client.post("/api/v1/citas", json=cita(ayer), headers=SEC)
        con_secretaria = client.post(
            "/api/v1/citas", json=cita(manana(16), profesional="sec-1"), headers=SEC
        )
        inactivo = client.post(
            "/api/v1/citas", json=cita(manana(16), profesional="baja"), headers=SEC
        )
        sin_zona = client.post("/api/v1/citas", json=cita("2030-01-01T10:00:00"), headers=SEC)
    assert pasada.status_code == 422
    assert con_secretaria.status_code == 422
    assert inactivo.status_code == 422
    assert sin_zona.status_code == 422


def test_cancelar_exige_motivo_y_estados_finales_no_cambian(settings: Settings) -> None:
    client, _ = preparar(settings)
    with client:
        creada = client.post("/api/v1/citas", json=cita(manana(10)), headers=SEC).json()
        ruta = f"/api/v1/citas/{creada['id_cita']}/estado"
        sin_motivo = client.post(ruta, json={"estado": "cancelada"}, headers=SEC)
        atendida_antes = client.post(ruta, json={"estado": "atendida"}, headers=SEC)
        cancelada = client.post(
            ruta, json={"estado": "cancelada", "motivo": "Paciente reprograma"}, headers=SEC
        )
        otra_vez = client.post(ruta, json={"estado": "cancelada", "motivo": "x"}, headers=SEC)
        inexistente = client.post(
            "/api/v1/citas/zzz/estado", json={"estado": "cancelada", "motivo": "x"}, headers=SEC
        )
    assert sin_motivo.status_code == 422
    assert atendida_antes.status_code == 422
    assert cancelada.status_code == 200
    assert cancelada.json()["estado"] == "cancelada"
    assert otra_vez.status_code == 409
    assert inexistente.status_code == 404


def test_rango_de_agenda_limitado(settings: Settings) -> None:
    client, _ = preparar(settings)
    lejos = (datetime.now(UTC) + timedelta(days=60)).isoformat()
    with client:
        response = client.get(
            "/api/v1/citas", params={"desde": manana(0), "hasta": lejos}, headers=SEC
        )
    assert response.status_code == 422


def test_odontograma_por_pieza_fdi(settings: Settings) -> None:
    client, _ = preparar(settings)
    with client:
        valida = client.put(
            "/api/v1/pacientes/p1/odontograma/piezas/36",
            json={"estado": "caries", "superficies": ["oclusal", "mesial"]},
            headers=ODO,
        )
        temporal_invalida = client.put(
            "/api/v1/pacientes/p1/odontograma/piezas/58", json={"estado": "sana"}, headers=ODO
        )
        superficie_invalida = client.put(
            "/api/v1/pacientes/p1/odontograma/piezas/11",
            json={"estado": "sana", "superficies": ["arriba"]},
            headers=ODO,
        )
        por_secretaria = client.put(
            "/api/v1/pacientes/p1/odontograma/piezas/11", json={"estado": "sana"}, headers=SEC
        )
        lectura = client.get("/api/v1/pacientes/p1/odontograma", headers=ODO)
    assert valida.status_code == 200
    assert valida.json()["actualizado_por"] == "odo-1"
    assert temporal_invalida.status_code == 422  # 58 no existe en FDI temporal
    assert superficie_invalida.status_code == 422
    assert por_secretaria.status_code == 403
    assert [p["pieza"] for p in lectura.json()["piezas"]] == ["36"]


def test_estado_de_pieza_debe_estar_en_la_lista_fija(settings: Settings) -> None:
    client, _ = preparar(settings)
    with client:
        libre = client.put(
            "/api/v1/pacientes/p1/odontograma/piezas/36", json={"estado": "Caries!"}, headers=ODO
        )
        mayuscula = client.put(
            "/api/v1/pacientes/p1/odontograma/piezas/36", json={"estado": "Caries"}, headers=ODO
        )
        todos = [
            client.put(
                "/api/v1/pacientes/p1/odontograma/piezas/36", json={"estado": e.value}, headers=ODO
            ).status_code
            for e in EstadoDental
        ]
    assert libre.status_code == 422
    assert mayuscula.status_code == 422  # el valor de la API va en minusculas
    assert set(todos) == {200}


def test_permisos_de_secretaria_no_incluyen_clinicos() -> None:
    assert not permisos.PERMISOS_POR_ROL["secretaria"] & permisos.PERMISOS_CLINICOS


def test_secretaria_no_puede_archivar_ni_siquiera_por_permiso_por_defecto() -> None:
    assert permisos.HISTORIALES_ARCHIVAR in permisos.PERMISOS_VEDADOS_SECRETARIA
    assert not permisos.PERMISOS_POR_ROL["secretaria"] & permisos.PERMISOS_VEDADOS_SECRETARIA


def test_secretaria_recibe_403_al_archivar(settings: Settings) -> None:
    client, _ = preparar(settings)
    with client:
        response = client.post(
            "/api/v1/pacientes/p1/archivo", json={"motivo": "traslado"}, headers=SEC
        )
    assert response.status_code == 403
