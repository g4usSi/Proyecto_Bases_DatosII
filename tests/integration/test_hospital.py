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
    "pagos:ver",
    "pagos:registrar",
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
    # Un cobro pagado ya no admite cambios (trigger): la limpieza los desactiva en su sesion.
    with admin.transaction():
        admin.execute("SET LOCAL session_replication_role = replica")
        for sql in (
            "DELETE FROM pago WHERE id_cobro IN "
            "(SELECT id_cobro FROM cobro WHERE id_atencion = ANY(%s))",
            "DELETE FROM detalle_cobro WHERE id_cobro IN "
            "(SELECT id_cobro FROM cobro WHERE id_atencion = ANY(%s))",
            "DELETE FROM cobro WHERE id_atencion = ANY(%s)",
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
    admin.execute(
        "DELETE FROM tarifa WHERE id_servicio IN "
        "(SELECT id_servicio FROM servicio WHERE nombre LIKE %s)",
        (marca + "%",),
    )
    admin.execute("DELETE FROM servicio WHERE nombre LIKE %s", (marca + "%",))
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


# ---------------------------------------------------------------------------------------
# Cobros y pagos
# ---------------------------------------------------------------------------------------


def servicio(admin, marca, nombre, general, personal=None, id_personal=None) -> int:
    id_servicio = admin.execute(
        "INSERT INTO servicio (nombre, tipo, unidad_cobro) VALUES (%s, 'Consulta', 'Por_evento') "
        "RETURNING id_servicio",
        (f"{marca} {nombre}",),
    ).fetchone()[0]
    admin.execute(
        "INSERT INTO tarifa (id_servicio, monto_vigente) VALUES (%s, %s)", (id_servicio, general)
    )
    if personal is not None:
        admin.execute(
            "INSERT INTO tarifa (id_servicio, id_personal, monto_vigente) VALUES (%s, %s, %s)",
            (id_servicio, id_personal, personal),
        )
    return id_servicio


def consulta(client, h, id_paciente) -> str:
    respuesta = client.post(
        f"/api/v1/pacientes/{id_paciente}/consultas", json={"motivo": "Control"}, headers=h
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["id_consulta"]


def test_cobro_con_tarifa_congelada_pagos_y_saldo(hospital, admin):
    with TestClient(create_app(Settings())) as client:
        identificador, correo = hospital.cuenta()
        h = entrar(client, correo)
        id_personal = admin.execute(
            "SELECT id_personal FROM personal_medico WHERE id_profesional_central = %s",
            (identificador,),
        ).fetchone()[0]
        consulta_general = servicio(
            admin, hospital.marca, "Consulta", "100.00", "80.00", id_personal
        )
        curacion = servicio(admin, hospital.marca, "Curacion", "35.50")
        servicios = client.get("/api/v1/servicios", headers=h).json()
        propio = next(s for s in servicios if s["id_servicio"] == consulta_general)
        assert propio["tarifa_general"] == "100.00"

        ana = paciente(client, h, hospital.marca)
        id_atencion = consulta(client, h, ana)
        abierto = client.post(
            f"/api/v1/pacientes/{ana}/cobros",
            json={"id_atencion": id_atencion, "descripcion": "Consulta general"},
            headers=h,
        )
        assert abierto.status_code == 201, abierto.text
        cobro = abierto.json()
        assert (cobro["estado"], cobro["total"], cobro["saldo"]) == ("abierto", "0", "0")
        ruta = f"/api/v1/pacientes/{ana}/cobros/{cobro['id_cobro']}"
        duplicado = client.post(
            f"/api/v1/pacientes/{ana}/cobros", json={"id_atencion": id_atencion}, headers=h
        )
        assert duplicado.status_code == 409

        # El precio sale de la tarifa del profesional de la atencion (80), no de la general.
        cargo = client.post(
            f"{ruta}/cargos", json={"id_servicio": consulta_general, "cantidad": 2}, headers=h
        ).json()
        assert cargo["total"] == "160.00" and cargo["cargos"][0]["precio_unitario"] == "80.00"
        cargo = client.post(f"{ruta}/cargos", json={"id_servicio": curacion}, headers=h).json()
        assert cargo["total"] == "195.50"
        assert cargo["cargos"][1]["concepto"] == f"{hospital.marca} Curacion"
        con_precio = client.post(
            f"{ruta}/cargos", json={"id_servicio": curacion, "precio_unitario": "1"}, headers=h
        )
        sin_servicio = client.post(f"{ruta}/cargos", json={"concepto": "Otro"}, headers=h)
        fraccion = client.post(
            f"{ruta}/cargos", json={"id_servicio": curacion, "cantidad": "1.5"}, headers=h
        )
        inexistente = client.post(f"{ruta}/cargos", json={"id_servicio": 2_000_000}, headers=h)
        assert {con_precio.status_code, sin_servicio.status_code, fraccion.status_code} == {422}
        assert inexistente.status_code == 422
        # Si la tarifa cambia despues, el cargo ya registrado no cambia (precio congelado).
        admin.execute(
            "UPDATE tarifa SET monto_vigente = 999 WHERE id_servicio = %s", (consulta_general,)
        )

        pago = client.post(
            f"{ruta}/pagos",
            json={"metodo": "efectivo", "monto": "150.00", "referencia": "R-1"},
            headers=h,
        ).json()
        assert (pago["pagado"], pago["saldo"], pago["estado"]) == ("150.00", "45.50", "abierto")
        assert pago["cargos"][0]["precio_unitario"] == "80.00"
        exceso = client.post(f"{ruta}/pagos", json={"metodo": "tarjeta", "monto": "50"}, headers=h)
        assert exceso.status_code == 409 and "excede" in exceso.text
        centavos = client.post(
            f"{ruta}/pagos", json={"metodo": "tarjeta", "monto": "1.001"}, headers=h
        )
        assert centavos.status_code == 422
        id_pago = pago["pagos"][0]["id_pago"]
        anulado = client.post(f"{ruta}/pagos/{id_pago}/anular", headers=h).json()
        assert anulado["pagado"] == "0" and anulado["pagos"][0]["anulado"] is True
        assert client.post(f"{ruta}/pagos/{id_pago}/anular", headers=h).status_code == 409
        pagado = client.post(
            f"{ruta}/pagos", json={"metodo": "transferencia", "monto": "195.50"}, headers=h
        ).json()
        assert (pagado["estado"], pagado["saldo"]) == ("pagado", "0.00")
        resumen = client.get("/api/v1/cobros/resumen", headers=h)
        assert resumen.status_code == 200, resumen.text
        assert resumen.json()["cobrado_hoy"] == "195.50"
        assert resumen.json()["cobrado_hoy_por_metodo"]["transferencia"] == "195.50"
        assert resumen.json()["pagos_anulados"] == 1
        assert resumen.json()["cobros_por_estado"]["pagado"] == 1
        assert pagado["cerrado_en"] is not None
        assert (
            client.post(f"{ruta}/cargos", json={"id_servicio": curacion}, headers=h).status_code
            == 409
        )
        assert client.post(f"{ruta}/anular", headers=h).status_code == 409

        tablero = client.get("/api/v1/cobros", params={"estado": "pagado"}, headers=h).json()
        assert cobro["id_cobro"] in [c["id_cobro"] for c in tablero]
        assert [
            c["id_cobro"] for c in client.get(f"/api/v1/pacientes/{ana}/cobros", headers=h).json()
        ] == [cobro["id_cobro"]]
        assert client.get(ruta, headers=h).json() == pagado
        ajeno = paciente(client, h, hospital.marca, "Beto")
        assert (
            client.get(
                f"/api/v1/pacientes/{ajeno}/cobros/{cobro['id_cobro']}", headers=h
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/pacientes/{ajeno}/cobros", json={"id_atencion": id_atencion}, headers=h
            ).status_code
            == 404
        )


def test_cerrar_y_anular_cobros(hospital, admin):
    with TestClient(create_app(Settings())) as client:
        _, correo = hospital.cuenta()
        h = entrar(client, correo)
        curacion = servicio(admin, hospital.marca, "Curacion", "40.00")
        ana = paciente(client, h, hospital.marca)
        rutas = []
        for _ in range(2):
            cobro = client.post(
                f"/api/v1/pacientes/{ana}/cobros",
                json={"id_atencion": consulta(client, h, ana)},
                headers=h,
            ).json()
            ruta = f"/api/v1/pacientes/{ana}/cobros/{cobro['id_cobro']}"
            client.post(f"{ruta}/cargos", json={"id_servicio": curacion}, headers=h)
            rutas.append(ruta)
        cerrado = client.post(f"{rutas[0]}/cerrar", headers=h).json()
        assert cerrado["estado"] == "cerrado"
        assert (
            client.post(f"{rutas[0]}/cargos", json={"id_servicio": curacion}, headers=h).status_code
            == 409
        )
        client.post(f"{rutas[0]}/pagos", json={"metodo": "efectivo", "monto": "10"}, headers=h)
        assert client.post(f"{rutas[0]}/anular", headers=h).status_code == 409  # tiene pagos
        anulado = client.post(f"{rutas[1]}/anular", headers=h).json()
        assert anulado["estado"] == "anulado"
        sin_pago = client.post(
            f"{rutas[1]}/pagos", json={"metodo": "efectivo", "monto": "1"}, headers=h
        )
        assert sin_pago.status_code == 409


def test_dos_pagos_simultaneos_no_exceden_el_total(hospital, admin):
    with TestClient(create_app(Settings())) as client:
        _, correo = hospital.cuenta()
        h = entrar(client, correo)
        curacion = servicio(admin, hospital.marca, "Curacion", "150.00")
        ana = paciente(client, h, hospital.marca)
        cobro = client.post(
            f"/api/v1/pacientes/{ana}/cobros",
            json={"id_atencion": consulta(client, h, ana)},
            headers=h,
        ).json()
        ruta = f"/api/v1/pacientes/{ana}/cobros/{cobro['id_cobro']}"
        client.post(f"{ruta}/cargos", json={"id_servicio": curacion}, headers=h)
        resultados = []
        barrera = threading.Barrier(2)

        def pagar():
            barrera.wait(timeout=10)
            resultados.append(
                client.post(
                    f"{ruta}/pagos", json={"metodo": "efectivo", "monto": "100"}, headers=h
                ).status_code
            )

        hilos = [threading.Thread(target=pagar) for _ in range(2)]
        [t.start() for t in hilos]
        [t.join(timeout=30) for t in hilos]
        assert sorted(resultados) == [200, 409]
        assert client.get(ruta, headers=h).json()["pagado"] == "100.00"


def test_permisos_de_pagos(hospital):
    with TestClient(create_app(Settings())) as client:
        _, solo_ver = hospital.cuenta(["pacientes:leer", "pagos:ver"])
        _, sin_pagos = hospital.cuenta(["pacientes:leer", "historiales:leer"])
        h_ver, h_sin = entrar(client, solo_ver), entrar(client, sin_pagos)
        assert client.get("/api/v1/cobros", headers=h_ver).status_code == 200
        assert (
            client.post(
                "/api/v1/pacientes/1/cobros", json={"id_atencion": "1"}, headers=h_ver
            ).status_code
            == 403
        )
        assert client.get("/api/v1/cobros", headers=h_sin).status_code == 403
        assert client.get("/api/v1/servicios", headers=h_sin).status_code == 403
