"""Hospital General (PostgreSQL) con datos sinteticos: se crean y se borran con la cuenta admin.

Requiere haber aplicado database/postgresql/008_escritura_api.sql.
"""

import threading
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from app.core.config import Settings
from app.domain.consulta import Diagnostico, NuevaConsulta, Receta, Tratamiento
from app.domain.errores import (
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
)
from app.domain.paciente import Alergia, Baja, Contacto, MotivoBaja, NuevoPaciente
from app.infrastructure.persistence.postgresql.unidad import UnidadTrabajoPostgreSQL
from app.main import create_app
from scripts.sincronizar_profesionales import sincronizar_hospital

PERMISOS = [
    "pacientes:leer",
    "pacientes:registrar",
    "historiales:leer",
    "consultas:registrar",
    "historiales:archivar",
]


@pytest.fixture
def admin(config_local):
    conexion = psycopg.connect(config_local["HISTORIALES_POSTGRES_ADMIN_DSN"], autocommit=True)
    yield conexion
    conexion.close()


@pytest.fixture
def hospital(config_local, admin):
    """Un profesional del Hospital General con cuenta central y sus pacientes de prueba."""
    marca = "Zzprueba" + uuid4().hex[:10]
    profesional = uuid4()
    correo = f"hospital-{profesional}@example.invalid"
    password = "Contrasena sintetica de prueba"
    admin.execute(
        "INSERT INTO identidad.profesional "
        "(id_profesional,correo,nombres,apellidos,password_hash,establecimiento,rol) "
        "VALUES (%s,%s,'Prueba','Medico',%s,'hospital_general','medico')",
        (profesional, correo, PasswordHash.recommended().hash(password)),
    )
    for permiso in PERMISOS:
        admin.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s,%s)", (profesional, permiso)
        )
    sincronizar_hospital(admin, [str(profesional)])

    class Entorno:
        pass

    entorno = Entorno()
    entorno.marca = marca
    entorno.profesional = str(profesional)
    entorno.correo = correo
    entorno.password = password
    entorno.dsn = config_local["HISTORIALES_POSTGRES_DSN"]
    entorno.unidad = lambda: UnidadTrabajoPostgreSQL(config_local["HISTORIALES_POSTGRES_DSN"])
    yield entorno

    pacientes = [
        f[0]
        for f in admin.execute(
            "SELECT id_paciente FROM paciente WHERE apellidos LIKE %s", (marca + "%",)
        )
    ]
    for tabla_hija, sql in (
        (
            "detalle_receta",
            "DELETE FROM detalle_receta WHERE id_receta IN (SELECT r.id_receta "
            "FROM receta r JOIN orden_medica o ON o.id_orden=r.id_orden "
            "JOIN atencion a ON a.id_atencion=o.id_atencion WHERE a.id_paciente = ANY(%s))",
        ),
        (
            "receta",
            "DELETE FROM receta WHERE id_orden IN (SELECT o.id_orden FROM orden_medica o "
            "JOIN atencion a ON a.id_atencion=o.id_atencion WHERE a.id_paciente = ANY(%s))",
        ),
        (
            "orden",
            "DELETE FROM orden_medica WHERE id_atencion IN "
            "(SELECT id_atencion FROM atencion WHERE id_paciente = ANY(%s))",
        ),
        (
            "tratamiento",
            "DELETE FROM tratamiento WHERE id_diagnostico IN (SELECT d.id_diagnostico "
            "FROM diagnostico d JOIN atencion a ON a.id_atencion=d.id_atencion "
            "WHERE a.id_paciente = ANY(%s))",
        ),
        (
            "diagnostico",
            "DELETE FROM diagnostico WHERE id_atencion IN "
            "(SELECT id_atencion FROM atencion WHERE id_paciente = ANY(%s))",
        ),
        ("atencion", "DELETE FROM atencion WHERE id_paciente = ANY(%s)"),
        ("alergia", "DELETE FROM paciente_alergia WHERE id_paciente = ANY(%s)"),
        ("paciente", "DELETE FROM paciente WHERE id_paciente = ANY(%s)"),
    ):
        admin.execute(sql, (pacientes,))
    admin.execute("DELETE FROM personal_medico WHERE id_profesional_central = %s", (profesional,))
    admin.execute("DELETE FROM identidad.profesional WHERE id_profesional = %s", (profesional,))


def registrar(hospital, nombres="Ana", **extra) -> str:
    with hospital.unidad() as unidad:
        paciente = unidad.pacientes.registrar(
            NuevoPaciente(nombres, hospital.marca, date(1990, 5, 1), **extra)
        )
        unidad.commit()
    return paciente.id_paciente


def test_registrar_leer_con_contacto_y_alergias(hospital):
    identificador = registrar(
        hospital,
        contacto=Contacto(telefono="5555-0000", correo="a@example.invalid"),
        alergias=(Alergia("Penicilina", "Urticaria", "grave"), Alergia("Latex")),
    )
    with hospital.unidad() as unidad:
        paciente = unidad.pacientes.obtener_por_id(identificador)
    assert paciente.fecha_nacimiento == date(1990, 5, 1)
    assert paciente.contacto == Contacto("5555-0000", "a@example.invalid", None)
    assert [a.sustancia for a in paciente.alergias] == ["Latex", "Penicilina"]
    assert paciente.archivado is False


def test_alergias_no_evaluadas_y_evaluadas_sin_alergias_son_distintas(hospital):
    sin_evaluar = registrar(hospital, "Sin")
    sin_alergias = registrar(hospital, "Cero", alergias=())
    with hospital.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(sin_evaluar).alergias is None
        assert unidad.pacientes.obtener_por_id(sin_alergias).alergias == ()
        assert unidad.pacientes.obtener_por_id(sin_evaluar).contacto is None


def test_sin_commit_no_se_guarda_nada(hospital):
    with hospital.unidad() as unidad:
        creado = unidad.pacientes.registrar(NuevoPaciente("Fantasma", hospital.marca))
    with hospital.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(creado.id_paciente) is None


@pytest.mark.parametrize(
    "identificador", ["0", "-1", "abc", "1; DROP TABLE paciente", "99999999999"]
)
def test_identificadores_invalidos_no_existen(hospital, identificador):
    with hospital.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(identificador) is None
        assert unidad.historial.listar_consultas(identificador, 5) == []


def test_busqueda_por_nombre_regla_comun(hospital):
    maria = registrar(hospital, "María José")
    marco = registrar(hospital, "Marco")
    with hospital.unidad() as unidad:
        busca = lambda texto: unidad.pacientes.buscar(  # noqa: E731
            tuple(texto.lower().split()), 10
        )
        assert {p.id_paciente for p in busca(f"mar {hospital.marca.lower()}")} == {maria, marco}
        assert [p.id_paciente for p in busca(f"jose {hospital.marca.lower()}")] == [maria]
        assert busca(f"zzz {hospital.marca.lower()}") == []
        assert len(unidad.pacientes.buscar((hospital.marca.lower(),), 1)) == 1
        # Los comodines de LIKE se tratan como texto, no como patron.
        assert unidad.pacientes.buscar(("%",), 10) == []
        assert unidad.pacientes.buscar(("_",), 10) == []


def test_consulta_completa_atomica_y_leida_igual(hospital):
    identificador = registrar(hospital)
    nueva = NuevaConsulta(
        motivo="Dolor abdominal",
        notas="Sin fiebre",
        diagnosticos=(Diagnostico("Gastritis", "K29", "CIE-10"), Diagnostico("Deshidratacion")),
        tratamientos=(Tratamiento("Dieta blanda"), Tratamiento("Hidratacion oral")),
        recetas=(
            Receta("Omeprazol", "20 mg", "cada 24 h", "oral", 14, "En ayunas"),
            Receta("Suero oral", "1 sobre", "cada 8 h"),
        ),
    )
    with hospital.unidad() as unidad:
        creada = unidad.historial.registrar_consulta(identificador, hospital.profesional, nueva)
        unidad.commit()
    with hospital.unidad() as unidad:
        [leida] = unidad.historial.listar_consultas(identificador, 10)
    assert leida.id_consulta == creada.id_consulta
    assert leida.id_profesional == hospital.profesional
    assert leida.motivo == "Dolor abdominal" and leida.notas == "Sin fiebre"
    assert leida.diagnosticos == nueva.diagnosticos
    assert leida.tratamientos == nueva.tratamientos
    assert leida.recetas == nueva.recetas
    assert abs(leida.fecha_hora - datetime.now(UTC)) < timedelta(minutes=1)
    assert leida.fecha_hora.tzinfo is not None


def test_consulta_sin_commit_o_con_error_no_deja_filas_a_medias(hospital, admin):
    identificador = registrar(hospital)
    con_receta = NuevaConsulta("Control", recetas=(Receta("X", "1", "1"),))
    with hospital.unidad() as unidad:
        unidad.historial.registrar_consulta(identificador, hospital.profesional, con_receta)
    with hospital.unidad() as unidad:
        assert unidad.historial.listar_consultas(identificador, 10) == []
    assert admin.execute(
        "SELECT count(*) FROM atencion WHERE id_paciente = %s", (int(identificador),)
    ).fetchone() == (0,)


def test_tratamiento_exige_un_diagnostico_en_este_motor(hospital):
    identificador = registrar(hospital)
    with hospital.unidad() as unidad, pytest.raises(DatosInvalidos):
        unidad.historial.registrar_consulta(
            identificador,
            hospital.profesional,
            NuevaConsulta("X", tratamientos=(Tratamiento("Y"),)),
        )


def test_profesional_sin_vinculo_no_puede_registrar(hospital):
    identificador = registrar(hospital)
    with hospital.unidad() as unidad, pytest.raises(ProfesionalNoVinculado):
        unidad.historial.registrar_consulta(identificador, str(uuid4()), NuevaConsulta("X"))
    with hospital.unidad() as unidad, pytest.raises(ProfesionalNoVinculado):
        unidad.historial.registrar_consulta(identificador, "no-es-uuid", NuevaConsulta("X"))


def test_paginacion_por_cursor(hospital):
    identificador = registrar(hospital)
    for i in range(5):
        with hospital.unidad() as unidad:
            unidad.historial.registrar_consulta(
                identificador, hospital.profesional, NuevaConsulta(f"Consulta {i}")
            )
            unidad.commit()
    with hospital.unidad() as unidad:
        primera = unidad.historial.listar_consultas(identificador, 3)
        segunda = unidad.historial.listar_consultas(identificador, 3, primera[-1].fecha_hora)
    assert [c.motivo for c in primera] == ["Consulta 4", "Consulta 3", "Consulta 2"]
    assert [c.motivo for c in segunda] == ["Consulta 1", "Consulta 0"]


def test_archivar_es_condicional_y_bloquea_consultas(hospital, admin):
    identificador = registrar(hospital)
    baja = Baja(MotivoBaja.TRASLADO, hospital.profesional, datetime.now(UTC), "Otro hospital")
    with hospital.unidad() as unidad:
        unidad.pacientes.archivar(identificador, baja)
        unidad.commit()
    with hospital.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(identificador).archivado is True
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.archivar(identificador, baja)
        with pytest.raises(PacienteArchivado):
            unidad.historial.registrar_consulta(
                identificador, hospital.profesional, NuevaConsulta("X")
            )
        with pytest.raises(PacienteNoEncontrado):
            unidad.pacientes.archivar("999999999", baja)
    fila = admin.execute(
        "SELECT estado, motivo_baja, detalle_baja, archivado_por::text FROM paciente "
        "WHERE id_paciente = %s",
        (int(identificador),),
    ).fetchone()
    assert fila == ("Inactivo", "traslado", "Otro hospital", hospital.profesional)


def test_la_base_rechaza_atenciones_en_historial_archivado_aunque_se_salte_la_api(hospital, admin):
    identificador = int(registrar(hospital))
    admin.execute(
        "UPDATE paciente SET estado='Inactivo', fecha_baja=current_date, "
        "motivo_baja='administrativo' WHERE id_paciente = %s",
        (identificador,),
    )
    id_personal = admin.execute(
        "SELECT id_personal FROM personal_medico WHERE id_profesional_central = %s",
        (hospital.profesional,),
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute(
            "INSERT INTO atencion (id_paciente, id_personal, tipo_atencion) "
            "VALUES (%s, %s, 'CONSULTA')",
            (identificador, id_personal),
        )


def test_dos_bajas_simultaneas_solo_una_gana(hospital):
    identificador = registrar(hospital)
    resultados = []
    barrera = threading.Barrier(2)

    def dar_de_baja():
        baja = Baja(MotivoBaja.ADMINISTRATIVO, hospital.profesional, datetime.now(UTC))
        try:
            with hospital.unidad() as unidad:
                barrera.wait(timeout=10)
                unidad.pacientes.archivar(identificador, baja)
                unidad.commit()
            resultados.append("ok")
        except PacienteArchivado:
            resultados.append("archivado")

    hilos = [threading.Thread(target=dar_de_baja) for _ in range(2)]
    [h.start() for h in hilos]
    [h.join(timeout=20) for h in hilos]
    assert sorted(resultados) == ["archivado", "ok"]


def test_la_cuenta_de_la_api_no_puede_borrar_datos_clinicos(hospital):
    identificador = registrar(hospital)
    with hospital.unidad() as unidad:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            unidad.conexion.execute(
                "DELETE FROM paciente WHERE id_paciente = %s", (int(identificador),)
            )


def test_flujo_completo_por_la_api_con_login_real(hospital):
    with TestClient(create_app(Settings())) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": hospital.correo, "password": hospital.password}
        )
        assert login.status_code == 200
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        creado = client.post(
            "/api/v1/pacientes",
            json={
                "nombres": "Luisa",
                "apellidos": hospital.marca,
                "fecha_nacimiento": "2001-02-03",
                "contacto": {"telefono": "1234"},
                "alergias": [{"sustancia": "Polen"}],
            },
            headers=h,
        )
        assert creado.status_code == 201
        pid = creado.json()["id_paciente"]
        busqueda = client.get(
            "/api/v1/pacientes", params={"nombre": f"lui {hospital.marca}"}, headers=h
        )
        assert [f["id_paciente"] for f in busqueda.json()] == [pid]
        consulta = client.post(
            f"/api/v1/pacientes/{pid}/consultas",
            json={
                "motivo": "Tos",
                "diagnosticos": [{"descripcion": "Resfriado"}],
                "tratamientos": [{"descripcion": "Reposo"}],
                "recetas": [
                    {"medicamento": "Paracetamol", "dosis": "500 mg", "frecuencia": "c/8h"}
                ],
            },
            headers=h,
        )
        assert consulta.status_code == 201
        historial = client.get(f"/api/v1/pacientes/{pid}/historial", headers=h)
        assert historial.status_code == 200
        assert historial.json()["consultas"][0]["recetas"][0]["medicamento"] == "Paracetamol"
        assert historial.json()["paciente"]["alergias"] == [
            {"sustancia": "Polen", "reaccion": None, "severidad": None}
        ]
        baja = client.post(
            f"/api/v1/pacientes/{pid}/archivo", json={"motivo": "traslado"}, headers=h
        )
        assert baja.status_code == 200
        de_nuevo = client.post(
            f"/api/v1/pacientes/{pid}/archivo", json={"motivo": "traslado"}, headers=h
        )
        despues = client.post(f"/api/v1/pacientes/{pid}/consultas", json={"motivo": "X"}, headers=h)
        assert de_nuevo.status_code == 409 and despues.status_code == 409
        assert client.get(f"/api/v1/pacientes/{pid}", headers=h).json()["archivado"] is True
        # Citas y odontograma no aplican a este motor todavia.
        assert client.get(f"/api/v1/pacientes/{pid}/odontograma", headers=h).status_code == 501
