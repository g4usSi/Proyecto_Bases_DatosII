"""Centro Pediatrico (MySQL) con datos sinteticos en una base temporal.

La base temporal se crea con 001 + 002 + 004 y la cuenta de la API recibe exactamente los
permisos de 003 + 005, de modo que tambien se prueba lo que la API NO puede hacer.
"""

import re
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import psycopg
import pymysql
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from app.application.errores import IntegracionNoConfigurada, OperacionPendiente
from app.core.config import PROJECT_ROOT, Settings
from app.domain.cita import EstadoCita, NuevaCita
from app.domain.cobros import EstadoCobro, MetodoPago, NuevoCargo, NuevoPago
from app.domain.consulta import Adenda, Diagnostico, NuevaConsulta, Receta, Tratamiento
from app.domain.errores import (
    CitaNoEncontrada,
    ConflictoAgenda,
    ConflictoEstado,
    ConsultaNoEncontrada,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
    RegistroNoEncontrado,
)
from app.domain.paciente import (
    Alergia,
    Baja,
    CambiosPaciente,
    Contacto,
    MotivoBaja,
    NuevoPaciente,
)
from app.domain.pediatria import EstadoDosis, NuevoControl
from app.domain.tutores import NuevoTutor, Vinculo
from app.infrastructure.persistence.mysql.unidad import UnidadTrabajoMySQL
from app.main import create_app
from scripts.sincronizar_profesionales import sincronizar_centro_pediatrico
from tests.integration.conftest import ejecutar_script

PERMISOS = [
    "pacientes:leer",
    "pacientes:registrar",
    "historiales:leer",
    "consultas:registrar",
    "historiales:archivar",
    "citas:leer",
    "citas:gestionar",
    "pagos:ver",
    "pagos:registrar",
]


@pytest.fixture(scope="module")
def mysql_app(mysql_pruebas):
    """Cuenta limitada como la de produccion: mismos permisos que 003 + 005."""
    base = mysql_pruebas["database"]
    usuario = "app_" + uuid4().hex[:12]
    clave = "Clave-sintetica-" + uuid4().hex
    root = pymysql.connect(
        **{k: v for k, v in mysql_pruebas.items() if k not in ("database", "autocommit")},
        autocommit=True,
    )
    with root.cursor() as cursor:
        cursor.execute(f"CREATE USER '{usuario}'@'%' IDENTIFIED BY '{clave}'")
    for archivo in (
        "003_permisos.sql",
        "005_permisos_escritura.sql",
        "007_permisos_extensiones.sql",
        "009_permisos_pediatria.sql",
        "011_permisos_profesionales.sql",
        "012_permisos_cobros.sql",
        "014_permisos_tutores.sql",
        "016_permisos_facturacion.sql",
    ):
        texto = (PROJECT_ROOT / "database/mysql" / archivo).read_text(encoding="utf-8")
        texto = texto.replace("historiales_app", usuario)
        ruta = PROJECT_ROOT / ".pytest_cache" / f"mysql_{archivo}"
        ruta.parent.mkdir(exist_ok=True)
        ruta.write_text(texto, encoding="utf-8")
        ejecutar_script(root, ruta, base)
        ruta.unlink()
    try:
        yield {
            "host": mysql_pruebas["host"],
            "port": mysql_pruebas["port"],
            "user": usuario,
            "password": clave,
            "database": base,
        }
    finally:
        assert re.fullmatch(r"app_[0-9a-f]{12}", usuario)
        with root.cursor() as cursor:
            cursor.execute(f"DROP USER IF EXISTS '{usuario}'@'%'")
        root.close()


def _conectar(datos, **extra):
    return pymysql.connect(
        **datos, charset="utf8mb4", init_command="SET time_zone = '+00:00'", **extra
    )


@pytest.fixture
def admin_mysql(mysql_pruebas):
    conexion = pymysql.connect(**{**mysql_pruebas, "autocommit": True})
    yield conexion
    conexion.close()


@pytest.fixture
def admin_pg(config_local):
    conexion = psycopg.connect(config_local["HISTORIALES_POSTGRES_ADMIN_DSN"], autocommit=True)
    yield conexion
    conexion.close()


@pytest.fixture
def centro(config_local, mysql_app, admin_mysql, admin_pg):
    """Un profesional del Centro Pediatrico: cuenta central en PostgreSQL y medico en MySQL."""
    marca = "Zzprueba" + uuid4().hex[:10]
    profesional = uuid4()
    correo = f"pediatria-{profesional}@example.invalid"
    password = "Contrasena sintetica de prueba"
    admin_pg.execute(
        "INSERT INTO identidad.profesional "
        "(id_profesional,correo,nombres,apellidos,password_hash,establecimiento,rol) "
        "VALUES (%s,%s,'Prueba','Pediatra',%s,'centro_pediatrico','medico')",
        (profesional, correo, PasswordHash.recommended().hash(password)),
    )
    for permiso in PERMISOS:
        admin_pg.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s,%s)", (profesional, permiso)
        )
    sincronizar_centro_pediatrico(
        config_local["HISTORIALES_POSTGRES_ADMIN_DSN"], [str(profesional)], admin_mysql
    )

    class Entorno:
        pass

    entorno = Entorno()
    entorno.marca = marca
    entorno.profesional = str(profesional)
    entorno.correo = correo
    entorno.password = password
    entorno.datos = mysql_app
    entorno.admin = admin_mysql
    entorno.unidad = lambda: UnidadTrabajoMySQL(lambda: _conectar(mysql_app))
    yield entorno
    admin_pg.execute("DELETE FROM identidad.profesional WHERE id_profesional = %s", (profesional,))


def registrar(centro, nombres="Ana", **extra) -> str:
    extra.setdefault("fecha_nacimiento", date(2018, 5, 1))
    with centro.unidad() as unidad:
        paciente = unidad.pacientes.registrar(NuevoPaciente(nombres, centro.marca, **extra))
        unidad.commit()
    return paciente.id_paciente


def contar(centro, sql, *parametros) -> int:
    with centro.admin.cursor() as cursor:
        cursor.execute(sql, parametros)
        return cursor.fetchone()[0]


def test_registrar_leer_con_contacto_y_alergias(centro):
    identificador = registrar(
        centro,
        contacto=Contacto(telefono="5555-0000", correo="a@example.invalid"),
        alergias=(Alergia("Penicilina", "Urticaria", "grave"), Alergia("Latex")),
    )
    with centro.unidad() as unidad:
        paciente = unidad.pacientes.obtener_por_id(identificador)
    assert paciente.fecha_nacimiento == date(2018, 5, 1)
    assert paciente.contacto == Contacto("5555-0000", "a@example.invalid", None)
    assert [a.sustancia for a in paciente.alergias] == ["Latex", "Penicilina"]
    assert paciente.alergias[1] == Alergia("Penicilina", "Urticaria", "grave")
    assert paciente.archivado is False
    expediente = contar(
        centro,
        "SELECT COUNT(*) FROM paciente WHERE id_paciente = %s AND numero_expediente LIKE 'CP-%%'",
        identificador,
    )
    assert expediente == 1


def test_el_catalogo_de_alergias_se_reutiliza_sin_importar_mayusculas_ni_acentos(centro):
    sustancia = "Sustancia" + uuid4().hex[:8]
    registrar(centro, "Uno", alergias=(Alergia(sustancia),))
    segundo = registrar(centro, "Dos", alergias=(Alergia(sustancia.upper()),))
    assert (
        contar(centro, "SELECT COUNT(*) FROM alergias_conocidas WHERE nombre = %s", sustancia) == 1
    )
    with centro.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(segundo).alergias[0].sustancia == sustancia


def test_alergias_no_evaluadas_y_evaluadas_sin_alergias_son_distintas(centro):
    sin_evaluar = registrar(centro, "Sin")
    sin_alergias = registrar(centro, "Cero", alergias=())
    with centro.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(sin_evaluar).alergias is None
        assert unidad.pacientes.obtener_por_id(sin_alergias).alergias == ()
        assert unidad.pacientes.obtener_por_id(sin_evaluar).contacto is None


def test_sin_commit_no_se_guarda_nada(centro):
    with centro.unidad() as unidad:
        creado = unidad.pacientes.registrar(
            NuevoPaciente("Fantasma", centro.marca, date(2020, 1, 1))
        )
    with centro.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(creado.id_paciente) is None


def test_fecha_de_nacimiento_obligatoria_y_no_futura(centro):
    with centro.unidad() as unidad:
        with pytest.raises(DatosInvalidos):
            unidad.pacientes.registrar(NuevoPaciente("Sin fecha", centro.marca))
    with centro.unidad() as unidad:
        with pytest.raises(DatosInvalidos):
            unidad.pacientes.registrar(
                NuevoPaciente("Futuro", centro.marca, date.today() + timedelta(days=2))
            )


@pytest.mark.parametrize(
    "identificador", ["0", "-1", "abc", "1; DROP TABLE paciente", "99999999999"]
)
def test_identificadores_invalidos_no_existen(centro, identificador):
    with centro.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(identificador) is None
        assert unidad.historial.listar_consultas(identificador, 5) == []


def test_busqueda_por_nombre_regla_comun(centro):
    maria = registrar(centro, "María José")
    marco = registrar(centro, "Marco")
    marca = centro.marca.lower()
    with centro.unidad() as unidad:
        assert {p.id_paciente for p in unidad.pacientes.buscar(("mar", marca), 10)} == {
            maria,
            marco,
        }
        assert [p.id_paciente for p in unidad.pacientes.buscar(("jose", marca), 10)] == [maria]
        assert unidad.pacientes.buscar(("zzz", marca), 10) == []
        assert len(unidad.pacientes.buscar((marca,), 1)) == 1
        # Los comodines de LIKE se tratan como texto, no como patron.
        assert unidad.pacientes.buscar(("%",), 10) == []
        assert unidad.pacientes.buscar(("_",), 10) == []
        # Mitad de una palabra no cuenta: solo comienzos.
        assert unidad.pacientes.buscar(("aria", marca), 10) == []


def test_busqueda_orden_e_incluye_archivados(centro):
    primero = registrar(centro, "Berta")
    segundo = registrar(centro, "Alba")
    baja = Baja(MotivoBaja.ADMINISTRATIVO, centro.profesional, datetime.now(UTC))
    with centro.unidad() as unidad:
        unidad.pacientes.archivar(primero, baja)
        unidad.commit()
    with centro.unidad() as unidad:
        encontrados = unidad.pacientes.buscar((centro.marca.lower(),), 10)
    # Mismos apellidos: se ordena por nombres.
    assert [p.id_paciente for p in encontrados] == [segundo, primero]
    assert [p.archivado for p in encontrados] == [False, True]


def test_consulta_completa_atomica_y_leida_igual(centro):
    identificador = registrar(centro)
    nueva = NuevaConsulta(
        motivo="Fiebre de tres dias",
        notas="Sin vomitos",
        diagnosticos=(Diagnostico("Faringitis", "J02", "CIE-10"), Diagnostico("Deshidratacion")),
        tratamientos=(Tratamiento("Reposo"), Tratamiento("Hidratacion oral")),
        recetas=(
            Receta("Paracetamol", "10 mg/kg", "cada 8 h", "oral", 5, "Con alimentos"),
            Receta("Suero oral", "1 sobre", "cada 8 h"),
        ),
    )
    with centro.unidad() as unidad:
        creada = unidad.historial.registrar_consulta(identificador, centro.profesional, nueva)
        unidad.commit()
    with centro.unidad() as unidad:
        [leida] = unidad.historial.listar_consultas(identificador, 10)
    assert leida.id_consulta == creada.id_consulta
    assert leida.id_profesional == centro.profesional
    assert leida.motivo == "Fiebre de tres dias" and leida.notas == "Sin vomitos"
    assert leida.diagnosticos == nueva.diagnosticos
    assert leida.tratamientos == nueva.tratamientos
    assert leida.recetas == nueva.recetas
    assert abs(leida.fecha_hora - datetime.now(UTC)) < timedelta(minutes=1)
    assert leida.fecha_hora.tzinfo is not None
    # El primer diagnostico queda como principal.
    principal = contar(
        centro,
        "SELECT COUNT(*) FROM consulta_diagnostico WHERE id_consulta = %s AND es_principal "
        "AND descripcion = 'Faringitis'",
        creada.id_consulta,
    )
    assert principal == 1


def test_error_a_mitad_de_la_consulta_no_deja_filas_a_medias(centro):
    identificador = registrar(centro)
    mala = NuevaConsulta(
        "Control",
        diagnosticos=(Diagnostico("Algo"),),
        recetas=(Receta("X", "1", "1", duracion_dias=0),),  # viola ck_receta_duracion
    )
    with pytest.raises(IntegracionNoConfigurada):
        with centro.unidad() as unidad:
            unidad.historial.registrar_consulta(identificador, centro.profesional, mala)
            unidad.commit()
    assert (
        contar(centro, "SELECT COUNT(*) FROM consulta_medica WHERE id_paciente = %s", identificador)
        == 0
    )
    assert (
        contar(
            centro,
            "SELECT COUNT(*) FROM consulta_diagnostico d JOIN consulta_medica c "
            "ON c.id_consulta = d.id_consulta WHERE c.id_paciente = %s",
            identificador,
        )
        == 0
    )


def test_consulta_sin_commit_no_se_guarda(centro):
    identificador = registrar(centro)
    with centro.unidad() as unidad:
        unidad.historial.registrar_consulta(identificador, centro.profesional, NuevaConsulta("X"))
    with centro.unidad() as unidad:
        assert unidad.historial.listar_consultas(identificador, 10) == []


def test_profesional_sin_vinculo_o_inactivo_no_puede_registrar(centro):
    identificador = registrar(centro)
    with centro.unidad() as unidad, pytest.raises(ProfesionalNoVinculado):
        unidad.historial.registrar_consulta(identificador, str(uuid4()), NuevaConsulta("X"))
    with centro.unidad() as unidad, pytest.raises(ProfesionalNoVinculado):
        unidad.historial.registrar_consulta(identificador, "no-es-uuid", NuevaConsulta("X"))
    with centro.admin.cursor() as cursor:
        cursor.execute(
            "UPDATE medico SET activo = FALSE WHERE id_profesional_central = %s",
            (centro.profesional,),
        )
    with centro.unidad() as unidad, pytest.raises(ProfesionalNoVinculado):
        unidad.historial.registrar_consulta(identificador, centro.profesional, NuevaConsulta("X"))


def test_paciente_inexistente(centro):
    with centro.unidad() as unidad, pytest.raises(PacienteNoEncontrado):
        unidad.historial.registrar_consulta("999999999", centro.profesional, NuevaConsulta("X"))


def test_paginacion_por_cursor(centro):
    identificador = registrar(centro)
    for i in range(5):
        with centro.unidad() as unidad:
            unidad.historial.registrar_consulta(
                identificador, centro.profesional, NuevaConsulta(f"Consulta {i}")
            )
            unidad.commit()
    with centro.unidad() as unidad:
        primera = unidad.historial.listar_consultas(identificador, 3)
        segunda = unidad.historial.listar_consultas(identificador, 3, primera[-1].fecha_hora)
    assert [c.motivo for c in primera] == ["Consulta 4", "Consulta 3", "Consulta 2"]
    assert [c.motivo for c in segunda] == ["Consulta 1", "Consulta 0"]


def test_archivar_es_condicional_y_bloquea_consultas(centro):
    identificador = registrar(centro)
    baja = Baja(MotivoBaja.TRASLADO, centro.profesional, datetime.now(UTC), "Otro hospital")
    with centro.unidad() as unidad:
        unidad.pacientes.archivar(identificador, baja)
        unidad.commit()
    with centro.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(identificador).archivado is True
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.archivar(identificador, baja)
        with pytest.raises(PacienteArchivado):
            unidad.historial.registrar_consulta(
                identificador, centro.profesional, NuevaConsulta("X")
            )
        with pytest.raises(PacienteNoEncontrado):
            unidad.pacientes.archivar("999999999", baja)
        with pytest.raises(ProfesionalNoVinculado):
            unidad.pacientes.archivar(identificador, Baja(MotivoBaja.TRASLADO, "x", baja.fecha))
    with centro.admin.cursor() as cursor:
        cursor.execute(
            "SELECT archivado, motivo_baja, detalle_baja, archivado_por FROM paciente "
            "WHERE id_paciente = %s",
            (identificador,),
        )
        assert cursor.fetchone() == (1, "traslado", "Otro hospital", centro.profesional)


def test_la_base_rechaza_consultas_en_historial_archivado_aunque_se_salte_la_api(centro):
    identificador = registrar(centro)
    with centro.admin.cursor() as cursor:
        cursor.execute(
            "UPDATE paciente SET archivado = TRUE, fecha_baja = NOW(6), motivo_baja = 'x' "
            "WHERE id_paciente = %s",
            (identificador,),
        )
        cursor.execute(
            "SELECT id_medico FROM medico WHERE id_profesional_central = %s",
            (centro.profesional,),
        )
        id_medico = cursor.fetchone()[0]
        with pytest.raises(pymysql.err.OperationalError, match="archivado"):
            cursor.execute(
                "INSERT INTO consulta_medica (id_paciente, id_medico, motivo_consulta) "
                "VALUES (%s, %s, 'x')",
                (identificador, id_medico),
            )


def test_dos_bajas_simultaneas_solo_una_gana(centro):
    identificador = registrar(centro)
    resultados = []
    barrera = threading.Barrier(2)

    def dar_de_baja():
        baja = Baja(MotivoBaja.ADMINISTRATIVO, centro.profesional, datetime.now(UTC))
        try:
            with centro.unidad() as unidad:
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


def test_consulta_y_baja_simultaneas_nunca_dejan_consulta_en_historial_archivado(centro):
    identificador = registrar(centro)
    resultados = {}
    barrera = threading.Barrier(2)

    def consultar():
        try:
            with centro.unidad() as unidad:
                barrera.wait(timeout=10)
                unidad.historial.registrar_consulta(
                    identificador, centro.profesional, NuevaConsulta("Carrera")
                )
                unidad.commit()
            resultados["consulta"] = "ok"
        except PacienteArchivado:
            resultados["consulta"] = "rechazada"

    def archivar():
        baja = Baja(MotivoBaja.ADMINISTRATIVO, centro.profesional, datetime.now(UTC))
        with centro.unidad() as unidad:
            barrera.wait(timeout=10)
            unidad.pacientes.archivar(identificador, baja)
            unidad.commit()
        resultados["baja"] = "ok"

    hilos = [threading.Thread(target=consultar), threading.Thread(target=archivar)]
    [h.start() for h in hilos]
    [h.join(timeout=30) for h in hilos]
    assert resultados["baja"] == "ok"
    # Pasara una de dos cosas, ambas validas: la consulta se confirmo antes de la baja, o
    # se rechazo. Lo que nunca puede ocurrir es una consulta "ok" y ninguna fila guardada
    # (ni una fila guardada despues de la baja con la consulta rechazada).
    guardadas = contar(
        centro, "SELECT COUNT(*) FROM consulta_medica WHERE id_paciente = %s", identificador
    )
    assert guardadas == (1 if resultados["consulta"] == "ok" else 0)


def test_la_cuenta_de_la_api_tiene_permisos_minimos(centro):
    identificador = registrar(centro)
    conexion = _conectar(centro.datos)
    try:
        with conexion.cursor() as cursor:
            for sql in (
                "DELETE FROM paciente",
                "DELETE FROM consulta_medica",
                "UPDATE paciente SET numero_expediente = 'Otro'",
                "UPDATE cita SET inicio = NOW()",
                "UPDATE cita SET id_medico = 1",
                "UPDATE consulta_medica SET motivo_consulta = 'Otro'",
                "SELECT salario FROM medico",
                "INSERT INTO medico (nombre, apellido, colegiado, salario) VALUES ('a','b','c',1)",
                "UPDATE medico SET colegiado = 'otro'",
                "UPDATE facturacion SET total_pagado = 0",
                "DELETE FROM pago",
                "UPDATE pago SET monto = 1",
            ):
                with pytest.raises(pymysql.err.OperationalError) as error:
                    cursor.execute(sql)
                assert error.value.args[0] in (1142, 1143, 1054), sql
            cursor.execute("SELECT nombre FROM paciente WHERE id_paciente = %s", (identificador,))
            assert cursor.fetchone() is not None
    finally:
        conexion.close()


def test_sincronizacion_es_idempotente_y_respeta_el_colegiado(centro, config_local, admin_pg):
    dsn = config_local["HISTORIALES_POSTGRES_ADMIN_DSN"]
    consulta = (
        "SELECT COUNT(*), MAX(colegiado), MAX(activo) FROM medico WHERE id_profesional_central = %s"
    )
    with centro.admin.cursor() as cursor:
        cursor.execute(consulta, (centro.profesional,))
        total, colegiado, activo = cursor.fetchone()
        assert (total, colegiado, activo) == (1, f"PEND-{centro.profesional}", 1)
        cursor.execute(
            "UPDATE medico SET colegiado = 'COL-12345' WHERE id_profesional_central = %s",
            (centro.profesional,),
        )
    admin_pg.execute(
        "UPDATE identidad.profesional SET activo = FALSE WHERE id_profesional = %s",
        (centro.profesional,),
    )
    assert sincronizar_centro_pediatrico(dsn, [centro.profesional], centro.admin) == 1
    assert sincronizar_centro_pediatrico(dsn, [centro.profesional], centro.admin) == 1
    with centro.admin.cursor() as cursor:
        cursor.execute(consulta, (centro.profesional,))
        assert cursor.fetchone() == (1, "COL-12345", 0)


def test_flujo_completo_por_la_api_con_login_real(centro):
    configuracion = Settings(
        mysql_host=centro.datos["host"],
        mysql_port=centro.datos["port"],
        mysql_user=centro.datos["user"],
        mysql_password=centro.datos["password"],
        mysql_database=centro.datos["database"],
    )
    with TestClient(create_app(configuracion)) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": centro.correo, "password": centro.password}
        )
        assert login.status_code == 200
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        sin_fecha = client.post(
            "/api/v1/pacientes", json={"nombres": "Luisa", "apellidos": centro.marca}, headers=h
        )
        assert sin_fecha.status_code == 422
        creado = client.post(
            "/api/v1/pacientes",
            json={
                "nombres": "Luisa",
                "apellidos": centro.marca,
                "fecha_nacimiento": "2019-02-03",
                "contacto": {"telefono": "1234"},
                "alergias": [{"sustancia": "Polen"}],
            },
            headers=h,
        )
        assert creado.status_code == 201
        pid = creado.json()["id_paciente"]
        busqueda = client.get(
            "/api/v1/pacientes", params={"nombre": f"lui {centro.marca}"}, headers=h
        )
        assert [f["id_paciente"] for f in busqueda.json()] == [pid]
        consulta = client.post(
            f"/api/v1/pacientes/{pid}/consultas",
            json={
                "motivo": "Tos",
                "diagnosticos": [{"descripcion": "Resfriado"}],
                "tratamientos": [{"descripcion": "Reposo"}],
                "recetas": [{"medicamento": "Paracetamol", "dosis": "5 ml", "frecuencia": "c/8h"}],
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
        # Odontograma no aplica a este motor.
        assert client.get(f"/api/v1/pacientes/{pid}/odontograma", headers=h).status_code == 501


# ---------------------------------------------------------------------------------------
# Adendas, correccion de datos y citas (migraciones 006 y 007)
# ---------------------------------------------------------------------------------------


def consulta_base(centro, identificador) -> str:
    with centro.unidad() as unidad:
        creada = unidad.historial.registrar_consulta(
            identificador,
            centro.profesional,
            NuevaConsulta(
                "Fiebre",
                notas="Primera visita",
                diagnosticos=(Diagnostico("Viral"),),
            ),
        )
        unidad.commit()
    return creada.id_consulta


def test_adenda_agrega_diagnostico_tratamiento_receta_y_nota(centro):
    identificador = registrar(centro)
    id_consulta = consulta_base(centro, identificador)
    adenda = Adenda(
        nota="Cultivo negativo",
        diagnosticos=(Diagnostico("Faringitis", "J02", "CIE-10"),),
        tratamientos=(Tratamiento("Reposo"),),
        recetas=(Receta("Paracetamol", "5 ml", "c/8h", "oral", 3),),
    )
    with centro.unidad() as unidad:
        actualizada = unidad.historial.agregar_a_consulta(
            identificador, id_consulta, centro.profesional, adenda
        )
        unidad.commit()
    with centro.unidad() as unidad:
        leida = unidad.historial.obtener_consulta(identificador, id_consulta)
    assert leida == actualizada
    assert [d.descripcion for d in leida.diagnosticos] == ["Viral", "Faringitis"]
    assert [t.descripcion for t in leida.tratamientos] == ["Reposo"]
    assert leida.recetas == (Receta("Paracetamol", "5 ml", "c/8h", "oral", 3),)
    assert leida.notas.startswith("Primera visita\n\n[Adenda ")
    assert centro.profesional in leida.notas and "Cultivo negativo" in leida.notas
    # Sin notas previas, la adenda abre las notas sin lineas en blanco sobrantes.
    with centro.unidad() as unidad:
        sin_notas = unidad.historial.registrar_consulta(
            identificador, centro.profesional, NuevaConsulta("Control")
        )
        unidad.commit()
    with centro.unidad() as unidad:
        agregada = unidad.historial.agregar_a_consulta(
            identificador, sin_notas.id_consulta, centro.profesional, Adenda(nota="Aclaracion")
        )
        unidad.commit()
    assert agregada.notas.startswith("[Adenda ")


def test_adenda_no_deja_nada_sin_commit_ni_en_consultas_ajenas(centro):
    identificador, otro = registrar(centro), registrar(centro, "Otro")
    id_consulta = consulta_base(centro, identificador)
    with centro.unidad() as unidad:
        unidad.historial.agregar_a_consulta(
            identificador, id_consulta, centro.profesional, Adenda(nota="No se confirma")
        )
    with centro.unidad() as unidad:
        assert unidad.historial.obtener_consulta(identificador, id_consulta).notas == (
            "Primera visita"
        )
        for id_malo in (id_consulta, "999999999", "abc"):
            with pytest.raises(ConsultaNoEncontrada):
                unidad.historial.agregar_a_consulta(
                    otro, id_malo, centro.profesional, Adenda(nota="x")
                )
        assert unidad.historial.obtener_consulta(otro, id_consulta) is None


def test_adenda_en_historial_archivado_se_rechaza_y_la_base_lo_refuerza(centro):
    identificador = registrar(centro)
    id_consulta = consulta_base(centro, identificador)
    with centro.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.ADMINISTRATIVO, centro.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with centro.unidad() as unidad, pytest.raises(PacienteArchivado):
        unidad.historial.agregar_a_consulta(
            identificador, id_consulta, centro.profesional, Adenda(nota="x")
        )
    # Aunque alguien se salte la API, la base tampoco acepta material nuevo.
    with centro.admin.cursor() as cursor, pytest.raises(pymysql.err.OperationalError) as error:
        cursor.execute(
            "INSERT INTO consulta_diagnostico (id_consulta, descripcion) VALUES (%s, 'x')",
            (int(id_consulta),),
        )
    assert "archivado" in str(error.value)


def test_la_base_no_deja_reescribir_notas_ni_la_identidad_de_una_consulta(centro):
    identificador = registrar(centro)
    id_consulta = int(consulta_base(centro, identificador))
    with centro.admin.cursor() as cursor:
        for sql in (
            "UPDATE consulta_medica SET notas_medicas = 'otra cosa' WHERE id_consulta = %s",
            "UPDATE consulta_medica SET notas_medicas = 'primera visita' WHERE id_consulta = %s",
            "UPDATE consulta_medica SET motivo_consulta = 'Cambiado' WHERE id_consulta = %s",
        ):
            with pytest.raises(pymysql.err.OperationalError):
                cursor.execute(sql, (id_consulta,))
        cursor.execute(
            "UPDATE consulta_medica SET notas_medicas = CONCAT(notas_medicas, ' (anexo)') "
            "WHERE id_consulta = %s",
            (id_consulta,),
        )


def test_corregir_datos_del_paciente_y_agregar_alergias(centro):
    identificador = registrar(centro, contacto=Contacto(telefono="111"))
    with centro.unidad() as unidad:
        unidad.pacientes.actualizar(
            identificador,
            CambiosPaciente(
                nombres="Ana Maria",
                fecha_nacimiento=date(2017, 6, 2),
                contacto=Contacto(correo="nuevo@example.invalid"),
            ),
        )
        unidad.pacientes.agregar_alergias(identificador, (Alergia("Polen", "Estornudos"),))
        unidad.commit()
    with centro.unidad() as unidad:
        p = unidad.pacientes.obtener_por_id(identificador)
        assert (p.nombres, p.apellidos, p.fecha_nacimiento) == (
            "Ana Maria",
            centro.marca,
            date(2017, 6, 2),
        )
        assert p.contacto == Contacto(None, "nuevo@example.invalid", None)  # reemplazo total
        assert p.alergias == (Alergia("Polen", "Estornudos"),)
        with pytest.raises(DatosInvalidos):  # ya registrada (el catalogo ignora mayusculas)
            unidad.pacientes.agregar_alergias(identificador, (Alergia("POLEN"),))
    with centro.unidad() as unidad, pytest.raises(DatosInvalidos):
        unidad.pacientes.actualizar(
            identificador, CambiosPaciente(fecha_nacimiento=date.today() + timedelta(days=2))
        )
    with centro.unidad() as unidad, pytest.raises(PacienteNoEncontrado):
        unidad.pacientes.actualizar("999999999", CambiosPaciente(nombres="X"))
    # Un cambio que no modifica nada no se confunde con un historial archivado.
    with centro.unidad() as unidad:
        unidad.pacientes.actualizar(identificador, CambiosPaciente(nombres="Ana Maria"))


def test_no_se_corrigen_datos_de_un_historial_archivado(centro):
    identificador = registrar(centro)
    with centro.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.TRASLADO, centro.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with centro.unidad() as unidad:
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.actualizar(identificador, CambiosPaciente(nombres="Nuevo"))
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.agregar_alergias(identificador, (Alergia("Polen"),))


def manana(horas=9) -> datetime:
    base = datetime.now(UTC) + timedelta(days=3)
    return base.replace(hour=horas, minute=0, second=0, microsecond=0)


def nueva_cita(centro, paciente, inicio, minutos=30) -> NuevaCita:
    return NuevaCita(paciente, centro.profesional, inicio, minutos, "Control")


def test_profesional_local_visible_para_la_agenda(centro):
    with centro.unidad() as unidad:
        perfil = unidad.profesionales.obtener(centro.profesional)
        assert unidad.profesionales.obtener(str(uuid4())) is None
        assert unidad.profesionales.obtener("no-es-uuid") is None
    assert perfil.id_profesional == centro.profesional
    assert perfil.rol == "medico" and perfil.activo and perfil.atiende_pacientes


def test_cita_ida_y_vuelta_en_utc(centro):
    identificador = registrar(centro)
    inicio = manana(15)
    with centro.unidad() as unidad:
        cita = unidad.citas.agendar(
            nueva_cita(centro, identificador, inicio, 45), "Ana Prueba", centro.profesional
        )
        unidad.commit()
    assert cita.estado == EstadoCita.PROGRAMADA
    assert cita.inicio == inicio and cita.fin == inicio + timedelta(minutes=45)
    assert cita.nombre_paciente == f"Ana {centro.marca}"
    assert cita.id_profesional == centro.profesional and cita.creada_por == centro.profesional
    with centro.unidad() as unidad:
        assert unidad.citas.obtener(cita.id_cita) == cita
        assert unidad.citas.listar_agenda(
            inicio - timedelta(hours=1), inicio + timedelta(hours=1), centro.profesional
        ) == [cita]
        assert (
            unidad.citas.listar_agenda(inicio + timedelta(hours=1), inicio + timedelta(hours=2))
            == []
        )
        assert unidad.citas.listar_agenda(inicio, inicio + timedelta(hours=1), str(uuid4())) == []
        assert unidad.citas.listar_por_paciente(identificador, 10) == [cita]
        assert unidad.citas.obtener("999999999") is None


def test_citas_que_se_cruzan_chocan_y_cancelar_libera_el_horario(centro):
    a, b = registrar(centro), registrar(centro, "Beto")
    inicio = manana()
    with centro.unidad() as unidad:
        primera = unidad.citas.agendar(nueva_cita(centro, a, inicio), "A", centro.profesional)
        unidad.commit()
    with centro.unidad() as unidad, pytest.raises(ConflictoAgenda):
        unidad.citas.agendar(
            nueva_cita(centro, b, inicio + timedelta(minutes=10)), "B", centro.profesional
        )
    with centro.unidad() as unidad:  # justo al terminar la primera: no se cruza
        unidad.citas.agendar(
            nueva_cita(centro, b, inicio + timedelta(minutes=30)), "B", centro.profesional
        )
        unidad.commit()
    with centro.unidad() as unidad:
        cancelada = unidad.citas.cambiar_estado(
            primera.id_cita, EstadoCita.CANCELADA, centro.profesional, "Paciente avisa"
        )
        unidad.commit()
    assert cancelada.estado == EstadoCita.CANCELADA and cancelada.motivo_cambio == "Paciente avisa"
    with centro.unidad() as unidad:
        unidad.citas.agendar(nueva_cita(centro, b, inicio), "B", centro.profesional)
        unidad.commit()


def test_estados_de_cita_y_transiciones(centro):
    identificador = registrar(centro)
    with centro.unidad() as unidad:
        cita = unidad.citas.agendar(
            nueva_cita(centro, identificador, manana()), "A", centro.profesional
        )
        unidad.commit()
    with centro.unidad() as unidad:
        confirmada = unidad.citas.cambiar_estado(
            cita.id_cita, EstadoCita.CONFIRMADA, centro.profesional, None
        )
        unidad.commit()
        assert confirmada.estado == EstadoCita.CONFIRMADA
    with centro.unidad() as unidad, pytest.raises(ConflictoAgenda):  # sigue ocupando el horario
        unidad.citas.agendar(nueva_cita(centro, identificador, manana()), "A", centro.profesional)
    with centro.unidad() as unidad:
        unidad.citas.cambiar_estado(cita.id_cita, EstadoCita.NO_ASISTIO, centro.profesional, None)
        unidad.commit()
    with centro.unidad() as unidad:
        with pytest.raises(ConflictoAgenda):  # final: ya no cambia
            unidad.citas.cambiar_estado(cita.id_cita, EstadoCita.CANCELADA, centro.profesional, "x")
        with pytest.raises(CitaNoEncontrada):
            unidad.citas.cambiar_estado("999999999", EstadoCita.CANCELADA, centro.profesional, "x")


def test_cita_a_historial_archivado_o_profesional_inexistente(centro):
    identificador = registrar(centro)
    with centro.unidad() as unidad, pytest.raises(DatosInvalidos):
        unidad.citas.agendar(
            NuevaCita(identificador, str(uuid4()), manana(), 30, "x"), "A", centro.profesional
        )
    with centro.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.TRASLADO, centro.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with centro.unidad() as unidad, pytest.raises(PacienteArchivado):
        unidad.citas.agendar(nueva_cita(centro, identificador, manana()), "A", centro.profesional)


def test_dos_secretarias_reservando_el_mismo_horario_solo_una_gana(centro):
    a, b = registrar(centro), registrar(centro, "Beto")
    inicio = manana(18)
    resultados = []
    barrera = threading.Barrier(2)

    def reservar(paciente):
        try:
            with centro.unidad() as unidad:
                barrera.wait(timeout=10)
                unidad.citas.agendar(nueva_cita(centro, paciente, inicio), "X", centro.profesional)
                unidad.commit()
            resultados.append("ok")
        except ConflictoAgenda:
            resultados.append("choque")

    hilos = [threading.Thread(target=reservar, args=(p,)) for p in (a, b)]
    [h.start() for h in hilos]
    [h.join(timeout=30) for h in hilos]
    assert sorted(resultados) == ["choque", "ok"]


def test_flujo_de_adenda_correccion_y_citas_por_la_api(centro):
    configuracion = Settings(
        mysql_host=centro.datos["host"],
        mysql_port=centro.datos["port"],
        mysql_user=centro.datos["user"],
        mysql_password=centro.datos["password"],
        mysql_database=centro.datos["database"],
    )
    with TestClient(create_app(configuracion)) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": centro.correo, "password": centro.password}
        )
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        pid = client.post(
            "/api/v1/pacientes",
            json={"nombres": "Rosa", "apellidos": centro.marca, "fecha_nacimiento": "2019-02-03"},
            headers=h,
        ).json()["id_paciente"]
        consulta = client.post(
            f"/api/v1/pacientes/{pid}/consultas",
            json={"motivo": "Fiebre", "diagnosticos": [{"descripcion": "Viral"}]},
            headers=h,
        ).json()
        ruta = f"/api/v1/pacientes/{pid}/consultas/{consulta['id_consulta']}"
        assert client.post(ruta + "/adenda", json={}, headers=h).status_code == 422
        agregada = client.post(
            ruta + "/adenda",
            json={
                "nota": "Mejora",
                "recetas": [{"medicamento": "Paracetamol", "dosis": "5 ml", "frecuencia": "c/8h"}],
            },
            headers=h,
        )
        assert agregada.status_code == 200
        assert agregada.json()["recetas"][0]["medicamento"] == "Paracetamol"
        assert client.get(ruta, headers=h).json() == agregada.json()
        assert client.get(f"/api/v1/pacientes/{pid}/consultas/999999", headers=h).status_code == 404

        corregido = client.patch(
            f"/api/v1/pacientes/{pid}", json={"contacto": {"telefono": "7777"}}, headers=h
        )
        assert corregido.status_code == 200 and corregido.json()["contacto"]["telefono"] == "7777"
        alergias = client.post(
            f"/api/v1/pacientes/{pid}/alergias",
            json={"alergias": [{"sustancia": "Latex"}]},
            headers=h,
        )
        assert alergias.status_code == 200

        inicio = manana(16).isoformat()
        cuerpo = {
            "id_paciente": pid,
            "id_profesional": centro.profesional,
            "inicio": inicio,
            "duracion_minutos": 30,
            "motivo": "Control",
        }
        cita = client.post("/api/v1/citas", json=cuerpo, headers=h)
        assert cita.status_code == 201, cita.text
        assert client.post("/api/v1/citas", json=cuerpo, headers=h).status_code == 409
        agenda = client.get(
            "/api/v1/citas",
            params={
                "desde": manana(0).isoformat(),
                "hasta": manana(23).isoformat(),
                "id_profesional": centro.profesional,
            },
            headers=h,
        )
        assert [c["id_cita"] for c in agenda.json()] == [cita.json()["id_cita"]]
        cancelada = client.post(
            f"/api/v1/citas/{cita.json()['id_cita']}/estado",
            json={"estado": "cancelada", "motivo": "Se reprograma"},
            headers=h,
        )
        assert cancelada.status_code == 200 and cancelada.json()["estado"] == "cancelada"


# ---------------------------------------------------------------------------------------
# Modulo pediatrico: crecimiento y vacunacion (migraciones 008 y 009)
# ---------------------------------------------------------------------------------------


def cargar_vacuna(centro, edad_meses=2, existencias=5, vence=None, ingreso=None) -> tuple[int, int]:
    """El catalogo lo carga la cuenta administrativa; la API solo lo lee."""
    vence = vence or date.today() + timedelta(days=200)
    with centro.admin.cursor() as cursor:
        cursor.execute(
            "INSERT INTO nombre_vacuna (nombre, edad_recomendada_meses, dosis_sugerida) "
            "VALUES (%s, %s, '0.5 ml')",
            (f"Vacuna {centro.marca} {uuid4().hex[:8]}", edad_meses),
        )
        tipo = cursor.lastrowid
        cursor.execute(
            "INSERT INTO catalogo_vacunas (nombre_vacuna_fk, lote_vacuna, fecha_ingreso, "
            "fecha_vencimiento, cantidad, precio_unitario) VALUES (%s, %s, %s, %s, %s, 99.5)",
            (
                tipo,
                "L" + uuid4().hex[:8],
                ingreso or date.today() - timedelta(days=5),
                vence,
                existencias,
            ),
        )
        lote = cursor.lastrowid
    centro.admin.commit()
    return tipo, lote


def existencias(centro, lote) -> int:
    return contar(centro, "SELECT cantidad FROM catalogo_vacunas WHERE id_vacuna = %s", lote)


def test_controles_de_crecimiento_se_agregan_y_se_leen(centro):
    identificador = registrar(centro, fecha_nacimiento=date.today() - timedelta(days=400))
    with centro.unidad() as unidad:
        primero = unidad.crecimiento.registrar(
            identificador,
            NuevoControl(peso_kg=10.25, talla_cm=78.5, perimetro_cefalico=46.0, percentil_peso=50),
            datetime.now(UTC) - timedelta(hours=1),
            13,
        )
        segundo = unidad.crecimiento.registrar(
            identificador, NuevoControl(observaciones="Sin cambios"), datetime.now(UTC), 13
        )
        unidad.commit()
    with centro.unidad() as unidad:
        controles = unidad.crecimiento.listar(identificador, 10)
        assert unidad.crecimiento.listar("abc", 10) == []
    assert [c.id_control for c in controles] == [segundo.id_control, primero.id_control]
    assert (primero.peso_kg, primero.talla_cm, primero.edad_meses) == (10.25, 78.5, 13)
    assert controles[1].percentil_peso == 50 and controles[0].peso_kg is None


def test_control_rechaza_medidas_imposibles_archivados_y_pacientes_ajenos(centro):
    identificador = registrar(centro)
    with centro.unidad() as unidad, pytest.raises(DatosInvalidos):
        unidad.crecimiento.registrar(
            identificador, NuevoControl(percentil_peso=150), datetime.now(UTC), 1
        )
    with centro.unidad() as unidad, pytest.raises(DatosInvalidos):  # antes de nacer
        unidad.crecimiento.registrar(
            identificador, NuevoControl(peso_kg=3), datetime(2001, 1, 1, tzinfo=UTC), 0
        )
    with centro.unidad() as unidad, pytest.raises(PacienteNoEncontrado):
        unidad.crecimiento.registrar("999999999", NuevoControl(peso_kg=3), datetime.now(UTC), 0)
    with centro.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.TRASLADO, centro.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with centro.unidad() as unidad, pytest.raises(PacienteArchivado):
        unidad.crecimiento.registrar(identificador, NuevoControl(peso_kg=3), datetime.now(UTC), 1)


def test_un_control_no_se_modifica_ni_se_borra_ni_por_la_base(centro):
    identificador = registrar(centro)
    with centro.unidad() as unidad:
        control = unidad.crecimiento.registrar(
            identificador, NuevoControl(peso_kg=4), datetime.now(UTC), 0
        )
        unidad.commit()
    with centro.admin.cursor() as cursor:
        for sql in (
            "UPDATE control_crecimiento SET peso_kg = 9 WHERE id_control = %s",
            "DELETE FROM control_crecimiento WHERE id_control = %s",
        ):
            with pytest.raises(pymysql.err.OperationalError):
                cursor.execute(sql, (int(control.id_control),))
    # La cuenta de la API ni siquiera tiene el privilegio.
    conexion = _conectar(centro.datos)
    with conexion.cursor() as cursor, pytest.raises(pymysql.err.OperationalError) as error:
        cursor.execute("UPDATE control_crecimiento SET peso_kg = 9")
    assert error.value.args[0] == 1142  # ER_TABLEACCESS_DENIED_ERROR
    conexion.close()


def test_la_api_no_ve_precios_ni_cambia_el_catalogo(centro):
    tipo, lote = cargar_vacuna(centro)
    conexion = _conectar(centro.datos)
    with conexion.cursor() as cursor:
        cursor.execute("SELECT cantidad FROM catalogo_vacunas WHERE id_vacuna = %s", (lote,))
        assert cursor.fetchone()[0] == 5
        for sql in (
            "SELECT precio_unitario FROM catalogo_vacunas",
            "UPDATE catalogo_vacunas SET cantidad = 999",
            "INSERT INTO nombre_vacuna (nombre) VALUES ('x')",
            "DELETE FROM esquema_vacunacion",
        ):
            with pytest.raises(pymysql.err.OperationalError) as error:
                cursor.execute(sql)
            assert error.value.args[0] in (1142, 1143, 1227), sql
    conexion.close()


def test_catalogo_de_tipos_de_vacuna(centro):
    tipo, _ = cargar_vacuna(centro, edad_meses=2)
    otro, _ = cargar_vacuna(centro, edad_meses=None)
    with centro.unidad() as unidad:
        tipos = {t.id_vacuna: t for t in unidad.vacunacion.listar_tipos()}
        assert (
            tipos[str(tipo)].edad_recomendada_meses == 2
            and tipos[str(otro)].edad_recomendada_meses is None
        )


def test_programar_y_aplicar_queda_trazado_sin_stock(centro):
    identificador = registrar(centro)
    tipo, lote = cargar_vacuna(centro, existencias=2)
    programada = date.today() + timedelta(days=10)
    with centro.unidad() as unidad:
        dosis = unidad.vacunacion.programar(identificador, str(tipo), 1, programada)
        unidad.commit()
    assert dosis.estado == EstadoDosis.PENDIENTE and dosis.fecha_programada == programada
    assert dosis.id_aplicador is None
    with centro.unidad() as unidad:
        aplicada = unidad.vacunacion.aplicar(
            identificador, dosis.id_dosis, centro.profesional, datetime.now(UTC), "Leve fiebre"
        )
        unidad.commit()
    assert aplicada.estado == EstadoDosis.APLICADA and aplicada.id_aplicador == centro.profesional
    assert aplicada.fecha_aplicacion is not None
    assert aplicada.observaciones_reaccion == "Leve fiebre"
    assert existencias(centro, lote) == 2  # el stock no se toca
    with centro.unidad() as unidad:
        assert unidad.vacunacion.listar_esquema(identificador) == [aplicada]
        assert unidad.vacunacion.obtener_dosis(identificador, dosis.id_dosis) == aplicada
        assert unidad.vacunacion.obtener_dosis("999999999", dosis.id_dosis) is None
    # Aplicada es definitiva: ni la API ni la base la reescriben.
    with centro.unidad() as unidad, pytest.raises(ConflictoEstado):
        unidad.vacunacion.aplicar(
            identificador, dosis.id_dosis, centro.profesional, datetime.now(UTC), None
        )
    with centro.unidad() as unidad, pytest.raises(ConflictoEstado):
        unidad.vacunacion.cancelar(identificador, dosis.id_dosis)
    with centro.admin.cursor() as cursor, pytest.raises(pymysql.err.OperationalError):
        cursor.execute(
            "UPDATE esquema_vacunacion SET estado_aplicacion = 'Pendiente' WHERE id_esquema = %s",
            (int(dosis.id_dosis),),
        )


def test_sin_commit_no_se_aplica_y_aplicadores_invalidos(centro):
    identificador = registrar(centro)
    tipo, _ = cargar_vacuna(centro)
    with centro.unidad() as unidad:
        dosis = unidad.vacunacion.programar(identificador, str(tipo), 1, None)
        unidad.commit()
    ahora = datetime.now(UTC)
    with centro.unidad() as unidad:
        unidad.vacunacion.aplicar(identificador, dosis.id_dosis, centro.profesional, ahora, None)
    pendiente = (
        "SELECT estado_aplicacion = 'Pendiente' FROM esquema_vacunacion WHERE id_esquema = %s"
    )
    assert contar(centro, pendiente, int(dosis.id_dosis)) == 1  # no hubo commit
    with centro.unidad() as unidad, pytest.raises(ProfesionalNoVinculado):
        unidad.vacunacion.aplicar(identificador, dosis.id_dosis, str(uuid4()), ahora, None)
    with centro.unidad() as unidad, pytest.raises(RegistroNoEncontrado):
        unidad.vacunacion.aplicar("999999999", dosis.id_dosis, centro.profesional, ahora, None)


def test_cancelar_dosis_pendiente_y_programar_para_archivados(centro):
    identificador = registrar(centro)
    tipo, _ = cargar_vacuna(centro)
    with centro.unidad() as unidad:
        dosis = unidad.vacunacion.programar(identificador, str(tipo), 1, None)
        unidad.commit()
    with centro.unidad() as unidad:
        cancelada = unidad.vacunacion.cancelar(identificador, dosis.id_dosis)
        unidad.commit()
    assert cancelada.estado == EstadoDosis.CANCELADA
    with centro.unidad() as unidad:
        with pytest.raises(ConflictoEstado):
            unidad.vacunacion.cancelar(identificador, dosis.id_dosis)
        with pytest.raises(RegistroNoEncontrado):
            unidad.vacunacion.cancelar(identificador, "999999999")
        with pytest.raises(DatosInvalidos):  # la vacuna no existe en el catalogo
            unidad.vacunacion.programar(identificador, "999999999", 1, None)
    with centro.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.TRASLADO, centro.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with centro.unidad() as unidad, pytest.raises(PacienteArchivado):
        unidad.vacunacion.programar(identificador, str(tipo), 2, None)


def test_dos_aplicaciones_simultaneas_de_la_misma_dosis_solo_una_gana(centro):
    paciente = registrar(centro)
    tipo, _ = cargar_vacuna(centro)
    with centro.unidad() as unidad:
        dosis = unidad.vacunacion.programar(paciente, str(tipo), 1, None)
        unidad.commit()
    resultados = []
    barrera = threading.Barrier(2)

    def aplicar():
        try:
            with centro.unidad() as unidad:
                barrera.wait(timeout=10)
                unidad.vacunacion.aplicar(
                    paciente, dosis.id_dosis, centro.profesional, datetime.now(UTC), None
                )
                unidad.commit()
            resultados.append("ok")
        except ConflictoEstado:
            resultados.append("ya aplicada")

    hilos = [threading.Thread(target=aplicar) for _ in range(2)]
    [h.start() for h in hilos]
    [h.join(timeout=30) for h in hilos]
    assert sorted(resultados) == ["ok", "ya aplicada"]


def test_flujo_pediatrico_por_la_api(centro):
    configuracion = Settings(
        mysql_host=centro.datos["host"],
        mysql_port=centro.datos["port"],
        mysql_user=centro.datos["user"],
        mysql_password=centro.datos["password"],
        mysql_database=centro.datos["database"],
    )
    tipo, _ = cargar_vacuna(centro, edad_meses=2)
    with TestClient(create_app(configuracion)) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": centro.correo, "password": centro.password}
        )
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        pid = client.post(
            "/api/v1/pacientes",
            json={
                "nombres": "Rosa",
                "apellidos": centro.marca,
                "fecha_nacimiento": (date.today() - timedelta(days=100)).isoformat(),
            },
            headers=h,
        ).json()["id_paciente"]
        base = f"/api/v1/pacientes/{pid}"
        assert client.post(base + "/crecimiento", json={}, headers=h).status_code == 422
        assert (
            client.post(base + "/crecimiento", json={"peso_kg": -1}, headers=h).status_code == 422
        )
        control = client.post(
            base + "/crecimiento",
            json={"peso_kg": 6.4, "talla_cm": 61, "percentil_peso": 40},
            headers=h,
        )
        assert control.status_code == 201 and control.json()["edad_meses"] == 3
        assert [c["peso_kg"] for c in client.get(base + "/crecimiento", headers=h).json()] == [6.4]

        assert tipo in [
            int(t["id_vacuna"]) for t in client.get("/api/v1/vacunas", headers=h).json()
        ]
        assert client.get(f"/api/v1/vacunas/{tipo}/lotes", headers=h).status_code == 404

        generado = client.post(base + "/vacunacion/esquema-recomendado", headers=h)
        assert generado.status_code == 201
        propias = [d for d in generado.json() if d["id_vacuna"] == str(tipo)]
        assert len(propias) == 1 and propias[0]["numero_dosis"] == 1
        # Repetirlo no duplica lo ya programado.
        repetido = client.post(base + "/vacunacion/esquema-recomendado", headers=h).json()
        assert all(d["id_vacuna"] != str(tipo) for d in repetido)
        assert (
            client.post(
                base + "/vacunacion", json={"id_vacuna": str(tipo), "numero_dosis": 1}, headers=h
            ).status_code
            == 409
        )
        id_dosis = propias[0]["id_dosis"]
        aplicada = client.post(
            f"{base}/vacunacion/{id_dosis}/aplicar",
            json={"observaciones_reaccion": "Ninguna"},
            headers=h,
        )
        assert aplicada.status_code == 200, aplicada.text
        assert aplicada.json()["estado"] == "aplicada" and "lote" not in aplicada.json()
        assert client.post(f"{base}/vacunacion/{id_dosis}/cancelar", headers=h).status_code == 409
        assert (
            client.post(f"{base}/vacunacion/999999/aplicar", json={}, headers=h).status_code == 404
        )
        esquema = client.get(base + "/vacunacion", headers=h).json()
        assert {d["estado"] for d in esquema if d["id_dosis"] == id_dosis} == {"aplicada"}


def test_script_de_carga_de_vacunas_es_idempotente(centro):
    from scripts.cargar_catalogos import CatalogoInvalido, cargar_vacunas

    nombre = f"Vacuna {centro.marca}"
    datos = {"vacunas": [{"nombre": nombre, "edad_recomendada_meses": 2}]}
    assert cargar_vacunas(centro.admin, datos) == {"tipos_nuevos": 1, "tipos_actualizados": 0}
    datos["vacunas"][0]["edad_recomendada_meses"] = 4
    segunda = cargar_vacunas(centro.admin, datos)
    assert segunda == {"tipos_nuevos": 0, "tipos_actualizados": 1}
    assert (
        contar(centro, "SELECT edad_recomendada_meses FROM nombre_vacuna WHERE nombre = %s", nombre)
        == 4
    )
    for malo in ({}, {"vacunas": []}, {"vacunas": [{"nombre": " "}]}):
        with pytest.raises(CatalogoInvalido):
            cargar_vacunas(centro.admin, malo)


# ---------------------------------------------------------------------------------------
# Facturacion (contrato comun de cobros)
# ---------------------------------------------------------------------------------------


def test_facturacion_cargos_pagos_y_saldo(centro):
    identificador = registrar(centro)
    otro = registrar(centro, "Otro")
    id_consulta = consulta_base(centro, identificador)
    ahora = datetime.now(UTC)
    with centro.unidad() as unidad:
        with pytest.raises(RegistroNoEncontrado):  # la consulta es de otro paciente
            unidad.cobros.abrir(otro, id_consulta, None, ahora)
        cobro = unidad.cobros.abrir(identificador, id_consulta, "Consulta pediatrica", ahora)
        unidad.commit()
    assert (cobro.estado, cobro.total, cobro.descripcion) == (
        EstadoCobro.ABIERTO,
        Decimal("0"),
        "Consulta pediatrica",
    )
    with centro.unidad() as unidad, pytest.raises(ConflictoEstado):
        unidad.cobros.abrir(identificador, id_consulta, None, ahora)
    with centro.unidad() as unidad:
        with pytest.raises(DatosInvalidos):  # sin catalogo de servicios
            unidad.cobros.agregar_cargo(
                identificador, cobro.id_cobro, NuevoCargo(Decimal(1), id_servicio=1), ahora
            )
        unidad.cobros.agregar_cargo(
            identificador,
            cobro.id_cobro,
            NuevoCargo(Decimal("2"), concepto="Consulta", precio_unitario=Decimal("75.25")),
            ahora,
        )
        unidad.commit()
    with centro.unidad() as unidad:
        with pytest.raises(ConflictoEstado):
            unidad.cobros.registrar_pago(
                identificador, cobro.id_cobro, NuevoPago(MetodoPago.EFECTIVO, Decimal("200")), ahora
            )
    with centro.unidad() as unidad:
        with pytest.raises(DatosInvalidos):  # el centro no acepta cheques
            unidad.cobros.registrar_pago(
                identificador, cobro.id_cobro, NuevoPago(MetodoPago.CHEQUE, Decimal("1")), ahora
            )
    with centro.unidad() as unidad:
        parcial = unidad.cobros.registrar_pago(
            identificador,
            cobro.id_cobro,
            NuevoPago(MetodoPago.TARJETA, Decimal("100.50"), "AUT-1"),
            ahora,
        )
        unidad.commit()
    assert (parcial.total, parcial.pagado, parcial.saldo) == (
        Decimal("150.50"),
        Decimal("100.50"),
        Decimal("50.00"),
    )
    assert parcial.pagos[0].referencia == "AUT-1" and parcial.estado == EstadoCobro.ABIERTO
    with centro.unidad() as unidad:
        pagada = unidad.cobros.registrar_pago(
            identificador, cobro.id_cobro, NuevoPago(MetodoPago.EFECTIVO, Decimal("50")), ahora
        )
        unidad.commit()
        for operacion in (
            lambda: unidad.cobros.anular_pago(identificador, cobro.id_cobro, "1"),
            lambda: unidad.cobros.cerrar(identificador, cobro.id_cobro, ahora),
            lambda: unidad.cobros.listar_servicios(),
        ):
            with pytest.raises(OperacionPendiente):
                operacion()
        with pytest.raises(ConflictoEstado):  # con pagos no se anula (015)
            unidad.cobros.anular(identificador, cobro.id_cobro, ahora)
    assert pagada.estado == EstadoCobro.PAGADO and pagada.saldo == 0
    with centro.unidad() as unidad:
        pagadas = unidad.cobros.listar(None, frozenset({EstadoCobro.PAGADO}), 500)
        abiertas = unidad.cobros.listar(None, frozenset({EstadoCobro.ABIERTO}), 500)
        assert cobro.id_cobro in [c.id_cobro for c in pagadas]
        assert cobro.id_cobro not in [c.id_cobro for c in abiertas]
        assert unidad.cobros.listar(None, frozenset({EstadoCobro.ANULADO}), 500) == []
        assert [c.id_cobro for c in unidad.cobros.listar(identificador)] == [cobro.id_cobro]
        assert unidad.cobros.obtener(otro, cobro.id_cobro) is None


def test_dos_pagos_simultaneos_no_exceden_la_factura(centro):
    identificador = registrar(centro)
    ahora = datetime.now(UTC)
    with centro.unidad() as unidad:
        cobro = unidad.cobros.abrir(
            identificador, consulta_base(centro, identificador), None, ahora
        )
        unidad.cobros.agregar_cargo(
            identificador,
            cobro.id_cobro,
            NuevoCargo(Decimal(1), concepto="Vacuna", precio_unitario=Decimal("150")),
            ahora,
        )
        unidad.commit()
    resultados = []
    barrera = threading.Barrier(2)

    def pagar():
        try:
            with centro.unidad() as unidad:
                barrera.wait(timeout=10)
                unidad.cobros.registrar_pago(
                    identificador,
                    cobro.id_cobro,
                    NuevoPago(MetodoPago.EFECTIVO, Decimal("100")),
                    datetime.now(UTC),
                )
                unidad.commit()
            resultados.append("ok")
        except ConflictoEstado:
            resultados.append("excede")

    hilos = [threading.Thread(target=pagar) for _ in range(2)]
    [t.start() for t in hilos]
    [t.join(timeout=30) for t in hilos]
    assert sorted(resultados) == ["excede", "ok"]


def test_facturacion_por_la_api(centro):
    identificador = registrar(centro)
    id_consulta = consulta_base(centro, identificador)
    configuracion = Settings(
        mysql_host=centro.datos["host"],
        mysql_port=centro.datos["port"],
        mysql_user=centro.datos["user"],
        mysql_password=centro.datos["password"],
        mysql_database=centro.datos["database"],
    )
    with TestClient(create_app(configuracion)) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": centro.correo, "password": centro.password}
        )
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        cobro = client.post(
            f"/api/v1/pacientes/{identificador}/cobros",
            json={"id_atencion": id_consulta},
            headers=h,
        )
        assert cobro.status_code == 201, cobro.text
        ruta = f"/api/v1/pacientes/{identificador}/cobros/{cobro.json()['id_cobro']}"
        cargo = client.post(
            f"{ruta}/cargos",
            json={"concepto": "Control", "cantidad": "1", "precio_unitario": "80.00"},
            headers=h,
        )
        pago = client.post(f"{ruta}/pagos", json={"metodo": "efectivo", "monto": "80"}, headers=h)
        anular = client.post(f"{ruta}/anular", headers=h)
        servicios = client.get("/api/v1/servicios", headers=h)
    assert cargo.json()["total"] == "80.00"
    assert (pago.json()["estado"], pago.json()["saldo"]) == ("pagado", "0.00")
    assert anular.status_code == 409 and servicios.status_code == 501  # pagada: no se anula


def test_factura_a_nombre_del_tutor_y_anulacion(centro):
    """015: la factura queda a nombre del tutor principal (o del indicado) y se anula solo sin
    pagos; anulada ya no admite cargos ni pagos, ni siquiera saltandose la API."""
    identificador = registrar(centro)
    hermano = registrar(centro, "Hermano")
    consultas = [consulta_base(centro, identificador) for _ in range(3)]
    consulta_hermano = consulta_base(centro, hermano)
    ahora = datetime.now(UTC)
    with centro.unidad() as unidad:
        sin_tutor = unidad.cobros.abrir(identificador, consultas[0], None, ahora)
        madre = unidad.tutores.vincular(
            identificador,
            Vinculo("Madre", es_principal=True, autorizado=True),
            nuevo=NuevoTutor("Karina", "Barrios " + centro.marca, documento=uuid4().hex[:12]),
        )
        padre = unidad.tutores.vincular(
            identificador,
            Vinculo("Padre", es_principal=False, autorizado=True),
            nuevo=NuevoTutor("Julio", "Ruiz " + centro.marca, documento=uuid4().hex[:12]),
        )
        unidad.commit()
    assert sin_tutor.facturado_a is None
    with centro.unidad() as unidad:
        principal = unidad.cobros.abrir(identificador, consultas[1], None, ahora)
        elegido = unidad.cobros.abrir(
            identificador, consultas[2], None, ahora, padre.tutor.id_tutor
        )
        with pytest.raises(DatosInvalidos):  # tutor no vinculado a ese paciente
            unidad.cobros.abrir(hermano, consulta_hermano, None, ahora, padre.tutor.id_tutor)
        unidad.commit()
    assert principal.facturado_a.id_tutor == madre.tutor.id_tutor
    assert principal.facturado_a.nombre.startswith("Karina Barrios")
    assert elegido.facturado_a.id_tutor == padre.tutor.id_tutor

    with centro.unidad() as unidad:
        unidad.cobros.agregar_cargo(
            identificador,
            principal.id_cobro,
            NuevoCargo(Decimal(1), concepto="Control", precio_unitario=Decimal("180")),
            ahora,
        )
        anulada = unidad.cobros.anular(identificador, principal.id_cobro, ahora)
        unidad.commit()
    assert anulada.estado == EstadoCobro.ANULADO and anulada.cerrado_en is not None
    with centro.unidad() as unidad:
        with pytest.raises(ConflictoEstado):
            unidad.cobros.anular(identificador, principal.id_cobro, ahora)
        with pytest.raises(ConflictoEstado):
            unidad.cobros.agregar_cargo(
                identificador,
                principal.id_cobro,
                NuevoCargo(Decimal(1), concepto="Otro", precio_unitario=Decimal("1")),
                ahora,
            )
        with pytest.raises(ConflictoEstado):
            unidad.cobros.registrar_pago(
                identificador,
                principal.id_cobro,
                NuevoPago(MetodoPago.EFECTIVO, Decimal("1")),
                ahora,
            )
        anuladas = unidad.cobros.listar(None, frozenset({EstadoCobro.ANULADO}), 500)
        por_cobrar = unidad.cobros.listar(None, frozenset({EstadoCobro.ABIERTO}), 500)
        assert principal.id_cobro in [c.id_cobro for c in anuladas]
        assert principal.id_cobro not in [c.id_cobro for c in por_cobrar]

    # La base lo impone aunque se salte la API: ni cargos, ni reabrir, ni cambiar titular.
    with centro.admin.cursor() as cursor:
        for sentencia in (
            "INSERT INTO detalle_facturacion (id_facturacion, concepto, cantidad, "
            "precio_unitario) VALUES (%s, 'X', 1, 1)",
            "UPDATE facturacion SET anulada_en = NULL WHERE id_facturacion = %s",
            "UPDATE facturacion SET id_tutor_fk = NULL WHERE id_facturacion = %s",
        ):
            with pytest.raises(pymysql.MySQLError):
                cursor.execute(sentencia, (int(principal.id_cobro),))
        # Con pagos, el CHECK impide anular.
        cursor.execute(
            "INSERT INTO detalle_facturacion (id_facturacion, concepto, cantidad, precio_unitario) "
            "VALUES (%s, 'Y', 1, 10)",
            (int(elegido.id_cobro),),
        )
        cursor.execute(
            "INSERT INTO pago (id_facturacion, id_tipo_pago, monto) VALUES (%s, 1, 5)",
            (int(elegido.id_cobro),),
        )
        with pytest.raises(pymysql.MySQLError):
            cursor.execute(
                "UPDATE facturacion SET anulada_en = NOW(6) WHERE id_facturacion = %s",
                (int(elegido.id_cobro),),
            )
    # La cuenta de la API no puede borrar facturas ni tocar montos.
    with centro.unidad() as unidad, unidad.conexion.cursor() as cursor:
        for sentencia in (
            "DELETE FROM facturacion WHERE id_facturacion = %s",
            "UPDATE facturacion SET total_pagado = 0 WHERE id_facturacion = %s",
        ):
            with pytest.raises(pymysql.MySQLError):
                cursor.execute(sentencia, (int(elegido.id_cobro),))


def test_anular_factura_por_la_api(centro):
    identificador = registrar(centro)
    id_consulta = consulta_base(centro, identificador)
    configuracion = Settings(
        mysql_host=centro.datos["host"],
        mysql_port=centro.datos["port"],
        mysql_user=centro.datos["user"],
        mysql_password=centro.datos["password"],
        mysql_database=centro.datos["database"],
    )
    with TestClient(create_app(configuracion)) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": centro.correo, "password": centro.password}
        )
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        cobro = client.post(
            f"/api/v1/pacientes/{identificador}/cobros",
            json={"id_atencion": id_consulta},
            headers=h,
        ).json()
        ruta = f"/api/v1/pacientes/{identificador}/cobros/{cobro['id_cobro']}"
        client.post(
            f"{ruta}/cargos", json={"concepto": "Control", "precio_unitario": "80.00"}, headers=h
        )
        anular = client.post(f"{ruta}/anular", headers=h)
        pago = client.post(f"{ruta}/pagos", json={"metodo": "efectivo", "monto": "1"}, headers=h)
        tablero = client.get("/api/v1/cobros", params={"estado": "anulado"}, headers=h)
        otra = client.post(
            f"/api/v1/pacientes/{identificador}/cobros",
            json={"id_atencion": id_consulta},
            headers=h,
        )
    assert anular.status_code == 200 and anular.json()["estado"] == "anulado"
    assert pago.status_code == 409
    assert cobro["id_cobro"] in [c["id_cobro"] for c in tablero.json()]
    assert otra.status_code == 201  # una anulada no impide volver a facturar la consulta


# ---------------------------------------------------------------------------------------
# Tutores
# ---------------------------------------------------------------------------------------


def test_tutores_principal_unico_hermanos_y_autorizacion(centro):
    configuracion = Settings(
        mysql_host=centro.datos["host"],
        mysql_port=centro.datos["port"],
        mysql_user=centro.datos["user"],
        mysql_password=centro.datos["password"],
        mysql_database=centro.datos["database"],
    )
    documento = "DPI-" + uuid4().hex[:12]
    hermano_a, hermano_b = registrar(centro, "Lia"), registrar(centro, "Leo")
    with TestClient(create_app(configuracion)) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": centro.correo, "password": centro.password}
        )
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        ruta_a = f"/api/v1/pacientes/{hermano_a}/tutores"
        madre = client.post(
            ruta_a,
            json={
                "tutor": {
                    "nombres": "Marta",
                    "apellidos": centro.marca,
                    "documento": documento,
                    "telefono": "5555-1111",
                },
                "parentesco": "Madre",
                "es_principal": True,
            },
            headers=h,
        )
        assert madre.status_code == 201, madre.text
        id_madre = madre.json()["tutor"]["id_tutor"]
        assert madre.json()["es_principal"] and madre.json()["autorizado"]

        # Mismo documento: se busca y se vincula al hermano (tutor compartido).
        repetido = client.post(
            ruta_a.replace(hermano_a, hermano_b),
            json={
                "tutor": {"nombres": "X", "apellidos": "Y", "documento": documento},
                "parentesco": "Madre",
            },
            headers=h,
        )
        assert repetido.status_code == 409
        encontrado = client.get("/api/v1/tutores", params={"documento": documento}, headers=h)
        assert encontrado.json()["id_tutor"] == id_madre
        compartido = client.post(
            f"/api/v1/pacientes/{hermano_b}/tutores",
            json={"id_tutor": id_madre, "parentesco": "Madre", "es_principal": True},
            headers=h,
        )
        assert compartido.status_code == 201
        assert (
            client.post(
                ruta_a, json={"id_tutor": id_madre, "parentesco": "Madre"}, headers=h
            ).status_code
            == 409
        )

        # Un nuevo principal reemplaza al anterior (uno solo por paciente).
        abuelo = client.post(
            ruta_a,
            json={
                "tutor": {"nombres": "Jose", "apellidos": centro.marca},
                "parentesco": "Abuelo",
                "es_principal": True,
            },
            headers=h,
        ).json()
        lista = client.get(ruta_a, headers=h).json()
        assert [(t["tutor"]["nombres"], t["es_principal"]) for t in lista] == [
            ("Jose", True),
            ("Marta", False),
        ]
        # El contacto es del tutor: cambia tambien en el hermano.
        cambio = client.patch(
            f"{ruta_a}/{id_madre}", json={"telefono": "5555-2222", "autorizado": False}, headers=h
        )
        assert cambio.status_code == 200 and cambio.json()["autorizado"] is False
        del_hermano = client.get(f"/api/v1/pacientes/{hermano_b}/tutores", headers=h).json()
        assert del_hermano[0]["tutor"]["telefono"] == "5555-2222"
        assert del_hermano[0]["es_principal"] is True  # el otro paciente no cambia

        # Reglas: principal debe estar autorizado; vacio; inexistente.
        id_abuelo = abuelo["tutor"]["id_tutor"]
        assert (
            client.patch(f"{ruta_a}/{id_abuelo}", json={"autorizado": False}, headers=h).status_code
            == 422
        )
        assert client.patch(f"{ruta_a}/{id_abuelo}", json={}, headers=h).status_code == 422
        assert (
            client.patch(f"{ruta_a}/999999", json={"parentesco": "X"}, headers=h).status_code == 404
        )
        assert (
            client.post(ruta_a, json={"parentesco": "Tio"}, headers=h).status_code == 422
        )  # ni id_tutor ni tutor

        # Historial archivado: se leen, pero no se cambian.
        client.post(
            f"/api/v1/pacientes/{hermano_a}/archivo", json={"motivo": "traslado"}, headers=h
        )
        assert client.get(ruta_a, headers=h).status_code == 200
        assert (
            client.patch(f"{ruta_a}/{id_madre}", json={"parentesco": "Mama"}, headers=h).status_code
            == 409
        )
    with centro.admin.cursor() as cursor:
        with pytest.raises(pymysql.err.OperationalError, match="archivado"):
            cursor.execute(
                "UPDATE paciente_tutor SET parentesco = 'X' WHERE id_paciente = %s",
                (hermano_a,),
            )
