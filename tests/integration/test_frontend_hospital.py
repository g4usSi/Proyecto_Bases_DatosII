"""Contratos propios del Hospital General para el mockup."""

from fastapi.testclient import TestClient

from app.core.config import PROJECT_ROOT, Settings
from app.main import create_app
from tests.integration.test_hospital import admin as admin
from tests.integration.test_hospital import consulta, entrar, paciente
from tests.integration.test_hospital import hospital as hospital


def test_atenciones_pulsera_y_perfil_del_hospital(hospital):
    with TestClient(create_app(Settings())) as client:
        id_profesional, correo = hospital.cuenta()
        h = entrar(client, correo)
        ana = paciente(client, h, hospital.marca)
        ajeno = paciente(client, h, hospital.marca, "Beto")
        consulta_id = consulta(client, h, ana)
        creado = client.post(
            f"/api/v1/pacientes/{ana}/ingresos",
            json={"id_cama": hospital.camas[0], "tipo": "emergencia", "motivo": "Observacion"},
            headers=h,
        )
        assert creado.status_code == 201, creado.text
        ingreso_id = creado.json()["id_ingreso"]
        listado = client.get(f"/api/v1/pacientes/{ana}/atenciones", headers=h)
        assert listado.status_code == 200, listado.text
        assert [a["tipo"] for a in listado.json()] == ["INGRESO", "CONSULTA"]
        assert [
            a["id_atencion"]
            for a in client.get(
                f"/api/v1/pacientes/{ana}/atenciones?antes_de={ingreso_id}", headers=h
            ).json()
        ] == [consulta_id]
        assert "saldo" not in listado.text and "precio" not in listado.text
        for identificador, campo in ((ingreso_id, "ingreso"), (consulta_id, "consulta")):
            ruta = f"/api/v1/pacientes/{ana}/atenciones/{identificador}"
            detalle = client.get(ruta, headers=h)
            assert detalle.status_code == 200 and detalle.json()[campo] is not None
            assert (
                client.get(
                    f"/api/v1/pacientes/{ajeno}/atenciones/{identificador}", headers=h
                ).status_code
                == 404
            )
        sangre = f"/api/v1/pacientes/{ana}/grupo-sanguineo"
        assert client.put(sangre, json={"grupo_sanguineo": "O+"}, headers=h).status_code == 200
        assert client.get(f"/api/v1/pacientes/{ana}", headers=h).json()["grupo_sanguineo"] == "O+"
        assert client.put(sangre, json={"grupo_sanguineo": "X+"}, headers=h).status_code == 422
        perfil = client.get("/api/v1/auth/perfil", headers=h)
        assert perfil.status_code == 200 and perfil.json()["correo"] == correo
        assert perfil.json()["hospital"]["estado"] == "Activo"
        assert (
            client.post(
                f"/api/v1/pacientes/{ana}/archivo", json={"motivo": "traslado"}, headers=h
            ).status_code
            == 200
        )
        assert client.put(sangre, json={"grupo_sanguineo": None}, headers=h).status_code == 409


def test_migracion_frontend_hospital_idempotente(admin):
    ruta = PROJECT_ROOT / "database/postgresql/016_frontend_hospital.sql"
    for _ in range(2):
        admin.execute(ruta.read_text(encoding="utf-8"))
