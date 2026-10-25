"""Hospital General (PostgreSQL): departamentos, camas, ingresos, ordenes, alta y resumen.

Datos sinteticos con una marca; se borran al terminar con la cuenta administrativa.
"""

import threading
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from app.core.config import Settings
from app.main import create_app
from scripts.sincronizar_profesionales import sincronizar_hospital

CLAVE = "Clave-hospital-2026"
PERMISOS = [
    "pacientes:leer",
    "pacientes:registrar",
    "historiales:leer",
    "consultas:registrar",
    "historiales:archivar",
    "camas:gestionar",
]


@pytest.fixture
def admin(config_local):
    conexion = psycopg.connect(config_local["HISTORIALES_POSTGRES_ADMIN_DSN"], autocommit=True)
    yield conexion
    conexion.close()


@pytest.fixture
def hospital(admin):
    marca = "Zzprueba" + uuid4().hex[:8]
    departamento = admin.execute(
        "INSERT INTO departamento (descripcion) VALUES (%s) RETURNING id_departamento",
        (f"{marca} Emergencias",),
    ).fetchone()[0]
    habitacion = admin.execute(
        "INSERT INTO habitacion (id_departamento, numero) VALUES (%s, 'E-1') "
        "RETURNING id_habitacion",
        (departamento,),
    ).fetchone()[0]
    camas = [
        admin.execute(
            "INSERT INTO cama (id_habitacion, codigo, estado_operativo) "
            "VALUES (%s, %s, 'Disponible') RETURNING id_cama",
            (habitacion, codigo),
        ).fetchone()[0]
        for codigo in ("E-1A", "E-1B")
    ]
    profesionales = []

    def cuenta(permisos=PERMISOS) -> tuple[str, str]:
        identificador = uuid4()
        correo = f"hosp-{identificador}@example.invalid"
        admin.execute(
            "INSERT INTO identidad.profesional (id_profesional, correo, nombres, apellidos, "
            "password_hash, establecimiento, rol) "
            "VALUES (%s, %s, 'Hugo', %s, %s, 'hospital_general', 'medico')",
            (identificador, correo, marca, PasswordHash.recommended().hash(CLAVE)),
        )
        for permiso in permisos:
            admin.execute(
                "INSERT INTO identidad.profesional_permiso VALUES (%s, %s)",
                (identificador, permiso),
            )
        sincronizar_hospital(admin, [str(identificador)])
        profesionales.append(identificador)
        return str(identificador), correo

    class Entorno:
        pass

    entorno = Entorno()
    entorno.marca = marca
    entorno.departamento = departamento
    entorno.camas = camas
    entorno.cuenta = cuenta
    yield entorno

    pacientes = [
        f[0]
        for f in admin.execute(
            "SELECT id_paciente FROM paciente WHERE apellidos LIKE %s", (marca + "%",)
        )
    ]
    atenciones = [
        f[0]
        for f in admin.execute(
            "SELECT id_atencion FROM atencion WHERE id_paciente = ANY(%s)", (pacientes,)
        )
    ]
    for sql in (
        "DELETE FROM detalle_receta WHERE id_receta IN (SELECT r.id_receta FROM receta r "
        "JOIN orden_medica o ON o.id_orden = r.id_orden WHERE o.id_atencion = ANY(%s))",
        "DELETE FROM receta WHERE id_orden IN "
        "(SELECT id_orden FROM orden_medica WHERE id_atencion = ANY(%s))",
        "DELETE FROM orden_medica WHERE id_atencion = ANY(%s)",
        "DELETE FROM diagnostico WHERE id_atencion = ANY(%s)",
        "DELETE FROM ingreso WHERE id_atencion = ANY(%s)",
        "DELETE FROM atencion WHERE id_atencion = ANY(%s)",
    ):
        admin.execute(sql, (atenciones,))
    admin.execute("DELETE FROM paciente WHERE id_paciente = ANY(%s)", (pacientes,))
    admin.execute("DELETE FROM cama WHERE id_cama = ANY(%s)", (camas,))
    admin.execute("DELETE FROM habitacion WHERE id_habitacion = %s", (habitacion,))
    admin.execute("DELETE FROM departamento WHERE id_departamento = %s", (departamento,))
    admin.execute(
        "DELETE FROM personal_medico WHERE id_profesional_central = ANY(%s)", (profesionales,)
    )
    admin.execute(
        "DELETE FROM identidad.profesional WHERE id_profesional = ANY(%s)", (profesionales,)
    )


def entrar(client, correo) -> dict[str, str]:
    respuesta = client.post("/api/v1/auth/login", json={"correo": correo, "password": CLAVE})
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def paciente(client, h, marca, nombres="Ana") -> str:
    respuesta = client.post(
        "/api/v1/pacientes", json={"nombres": nombres, "apellidos": marca}, headers=h
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id_paciente"]


def test_flujo_de_emergencia_completo(hospital, admin):
    cama_a, cama_b = hospital.camas
    with TestClient(create_app(Settings())) as client:
        _, correo = hospital.cuenta()
        h = entrar(client, correo)
        departamentos = client.get("/api/v1/departamentos", headers=h).json()
        propio = next(d for d in departamentos if d["id_departamento"] == hospital.departamento)
        assert (propio["habitaciones"], propio["camas"], propio["camas_disponibles"]) == (1, 2, 2)

        ana, beto = paciente(client, h, hospital.marca), paciente(client, h, hospital.marca, "Beto")
        antes = client.get("/api/v1/hospital/resumen", headers=h).json()
        ingreso = client.post(
            f"/api/v1/pacientes/{ana}/ingresos",
            json={
                "id_cama": cama_a,
                "tipo": "emergencia",
                "motivo": "Dolor toracico",
                "diagnosticos": [
                    {"descripcion": "Angina", "codigo": "I20", "sistema_codigo": "CIE-10"}
                ],
            },
            headers=h,
        )
        assert ingreso.status_code == 201, ingreso.text
        datos = ingreso.json()
        ruta = f"/api/v1/pacientes/{ana}/ingresos/{datos['id_ingreso']}"
        assert datos["abierto"] is True and datos["cama"] == "E-1A"
        assert datos["departamento"] == f"{hospital.marca} Emergencias"
        assert datos["diagnosticos"][0]["codigo"] == "I20"

        camas = client.get(
            "/api/v1/camas", params={"id_departamento": hospital.departamento}, headers=h
        ).json()
        ocupada = next(c for c in camas if c["id_cama"] == cama_a)
        assert ocupada["estado"] == "ocupada"
        assert ocupada["ocupante"]["nombre_paciente"] == f"Ana {hospital.marca}"
        disponibles = client.get(
            "/api/v1/camas",
            params={"id_departamento": hospital.departamento, "estado": "disponible"},
            headers=h,
        ).json()
        assert [c["id_cama"] for c in disponibles] == [cama_b]

        # Reglas: cama ocupada, paciente ya ingresado, estados manuales.
        otro = {"id_cama": cama_a, "tipo": "programado", "motivo": "X"}
        assert (
            client.post(f"/api/v1/pacientes/{beto}/ingresos", json=otro, headers=h).status_code
            == 409
        )
        doble = {"id_cama": cama_b, "tipo": "traslado", "motivo": "X"}
        assert (
            client.post(f"/api/v1/pacientes/{ana}/ingresos", json=doble, headers=h).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/camas/{cama_a}/estado", json={"estado": "limpieza"}, headers=h
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/camas/{cama_b}/estado", json={"estado": "ocupada"}, headers=h
            ).status_code
            == 422
        )
        inexistente = {"id_cama": 2_000_000_000, "tipo": "emergencia", "motivo": "X"}
        assert (
            client.post(
                f"/api/v1/pacientes/{beto}/ingresos", json=inexistente, headers=h
            ).status_code
            == 404
        )

        tablero = client.get("/api/v1/ingresos", params={"tipo": "emergencia"}, headers=h).json()
        assert datos["id_ingreso"] in [i["id_ingreso"] for i in tablero]
        despues = client.get("/api/v1/hospital/resumen", headers=h).json()
        assert despues["emergencias_abiertas"] == antes["emergencias_abiertas"] + 1
        assert despues["ingresos_hoy"] == antes["ingresos_hoy"] + 1
        assert despues["camas_por_estado"]["ocupada"] == antes["camas_por_estado"]["ocupada"] + 1
        assert 0 < despues["ocupacion"] <= 100

        # Durante el ingreso: diagnosticos y ordenes (solo agregar).
        diagnostico = client.post(
            f"{ruta}/diagnosticos", json={"descripcion": "Hipertension"}, headers=h
        )
        assert [d["descripcion"] for d in diagnostico.json()["diagnosticos"]] == [
            "Angina",
            "Hipertension",
        ]
        sin_descripcion = client.post(f"{ruta}/ordenes", json={"tipo": "examen"}, headers=h)
        assert sin_descripcion.status_code == 422
        examen = client.post(
            f"{ruta}/ordenes", json={"tipo": "examen", "descripcion": "Troponina"}, headers=h
        )
        medicamento = client.post(
            f"{ruta}/ordenes",
            json={
                "tipo": "medicamento",
                "recetas": [{"medicamento": "Aspirina", "dosis": "100 mg", "frecuencia": "c/24h"}],
            },
            headers=h,
        )
        ordenes = medicamento.json()["ordenes"]
        assert examen.status_code == 200 and [o["tipo"] for o in ordenes] == [
            "examen",
            "medicamento",
        ]
        assert ordenes[0]["descripcion"] == "Troponina"
        assert ordenes[1]["recetas"][0]["medicamento"] == "Aspirina"
        assert client.get(ruta, headers=h).json() == medicamento.json()
        historial = client.get(f"/api/v1/pacientes/{ana}/historial", headers=h).json()
        assert historial["consultas"] == []  # un ingreso no es una consulta

        # Alta: cierra una sola vez y la cama queda en limpieza.
        alta = client.post(f"{ruta}/alta", json={"motivo": "Estable"}, headers=h)
        assert alta.status_code == 200 and alta.json()["abierto"] is False
        assert client.post(f"{ruta}/alta", json={"motivo": "Otra"}, headers=h).status_code == 409
        assert (
            client.post(f"{ruta}/diagnosticos", json={"descripcion": "X"}, headers=h).status_code
            == 409
        )
        estado = admin.execute("SELECT estado_operativo FROM cama WHERE id_cama = %s", (cama_a,))
        assert estado.fetchone() == ("Limpieza",)
        lista = client.post(
            f"/api/v1/camas/{cama_a}/estado", json={"estado": "disponible"}, headers=h
        )
        assert lista.json()["estado"] == "disponible" and lista.json()["ocupante"] is None
        propios = client.get(f"/api/v1/pacientes/{ana}/ingresos", headers=h).json()
        assert [i["id_ingreso"] for i in propios] == [datos["id_ingreso"]]


def test_permisos_del_hospital(hospital):
    with TestClient(create_app(Settings())) as client:
        _, solo_lectura = hospital.cuenta(["pacientes:leer"])
        h = entrar(client, solo_lectura)
        assert client.get("/api/v1/camas", headers=h).status_code == 200
        assert client.get("/api/v1/hospital/resumen", headers=h).status_code == 200
        assert client.get("/api/v1/ingresos", headers=h).status_code == 403
        assert (
            client.post(
                f"/api/v1/camas/{hospital.camas[0]}/estado", json={"estado": "limpieza"}, headers=h
            ).status_code
            == 403
        )


def test_dos_ingresos_simultaneos_a_la_misma_cama(hospital):
    with TestClient(create_app(Settings())) as client:
        _, correo = hospital.cuenta()
        h = entrar(client, correo)
        pacientes = [paciente(client, h, hospital.marca, n) for n in ("Uno", "Dos")]
        resultados = []
        barrera = threading.Barrier(2)

        def ingresar(id_paciente):
            barrera.wait(timeout=10)
            resultados.append(
                client.post(
                    f"/api/v1/pacientes/{id_paciente}/ingresos",
                    json={"id_cama": hospital.camas[0], "tipo": "emergencia", "motivo": "X"},
                    headers=h,
                ).status_code
            )

        hilos = [threading.Thread(target=ingresar, args=(p,)) for p in pacientes]
        [t.start() for t in hilos]
        [t.join(timeout=30) for t in hilos]
    assert sorted(resultados) == [201, 409]


def test_historial_archivado_no_admite_ingresos_pero_si_el_alta(hospital):
    with TestClient(create_app(Settings())) as client:
        _, correo = hospital.cuenta()
        h = entrar(client, correo)
        ana = paciente(client, h, hospital.marca)
        ingreso = client.post(
            f"/api/v1/pacientes/{ana}/ingresos",
            json={"id_cama": hospital.camas[0], "tipo": "programado", "motivo": "Cirugia"},
            headers=h,
        ).json()
        assert (
            client.post(
                f"/api/v1/pacientes/{ana}/archivo", json={"motivo": "traslado"}, headers=h
            ).status_code
            == 200
        )
        ruta = f"/api/v1/pacientes/{ana}/ingresos/{ingreso['id_ingreso']}"
        assert (
            client.post(f"{ruta}/diagnosticos", json={"descripcion": "X"}, headers=h).status_code
            == 409
        )
        assert (
            client.post(f"{ruta}/alta", json={"motivo": "Traslado"}, headers=h).status_code == 200
        )
        nuevo = {"id_cama": hospital.camas[1], "tipo": "emergencia", "motivo": "X"}
        assert (
            client.post(f"/api/v1/pacientes/{ana}/ingresos", json=nuevo, headers=h).status_code
            == 409
        )


def test_la_base_impone_las_reglas_de_camas_aunque_se_salte_la_api(hospital, admin):
    cama_a, cama_b = hospital.camas
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute("UPDATE cama SET estado_operativo = 'Ocupada' WHERE id_cama = %s", (cama_a,))
    admin.execute(
        "UPDATE cama SET estado_operativo = 'Mantenimiento' WHERE id_cama = %s", (cama_b,)
    )
    id_paciente = admin.execute(
        "INSERT INTO paciente (nombres, apellidos) VALUES ('Sql', %s) RETURNING id_paciente",
        (hospital.marca,),
    ).fetchone()[0]
    id_personal = admin.execute(
        "INSERT INTO personal_medico (nombres, apellidos, rol) VALUES ('P', 'Zz', 'Medico') "
        "RETURNING id_personal"
    ).fetchone()[0]
    try:
        atencion = admin.execute(
            "INSERT INTO atencion (id_paciente, id_personal, tipo_atencion) "
            "VALUES (%s, %s, 'INGRESO') RETURNING id_atencion",
            (id_paciente, id_personal),
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):  # cama en mantenimiento
            admin.execute(
                "INSERT INTO ingreso (id_atencion, id_cama, fecha_hora_ingreso, tipo) "
                "VALUES (%s, %s, now(), 'Emergencia')",
                (atencion, cama_b),
            )
        admin.execute(
            "INSERT INTO ingreso (id_atencion, id_cama, fecha_hora_ingreso, tipo) "
            "VALUES (%s, %s, now(), 'Emergencia')",
            (atencion, cama_a),
        )
        assert admin.execute(
            "SELECT estado_operativo FROM cama WHERE id_cama = %s", (cama_a,)
        ).fetchone() == ("Ocupada",)
        with pytest.raises(psycopg.errors.CheckViolation):  # no se reasigna de cama
            admin.execute(
                "UPDATE ingreso SET id_cama = %s WHERE id_atencion = %s", (cama_b, atencion)
            )
        with pytest.raises(psycopg.errors.CheckViolation):  # alta sin motivo
            admin.execute(
                "UPDATE ingreso SET fecha_hora_alta = now() WHERE id_atencion = %s", (atencion,)
            )
        admin.execute(
            "UPDATE ingreso SET fecha_hora_alta = now(), motivo_alta = 'ok' WHERE id_atencion = %s",
            (atencion,),
        )
        with pytest.raises(psycopg.errors.CheckViolation):  # el alta no se cambia
            admin.execute(
                "UPDATE ingreso SET motivo_alta = 'otro' WHERE id_atencion = %s", (atencion,)
            )
    finally:
        admin.execute(
            "DELETE FROM ingreso WHERE id_atencion IN (SELECT id_atencion FROM atencion "
            "WHERE id_personal = %s)",
            (id_personal,),
        )
        admin.execute("DELETE FROM atencion WHERE id_personal = %s", (id_personal,))
        admin.execute("DELETE FROM personal_medico WHERE id_personal = %s", (id_personal,))
