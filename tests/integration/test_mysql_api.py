"""Centro Pediatrico (MySQL) con datos sinteticos en una base temporal.

La base temporal se crea con 001 + 002 + 004 y la cuenta de la API recibe exactamente los
permisos de 003 + 005, de modo que tambien se prueba lo que la API NO puede hacer.
"""

import re
import threading
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import psycopg
import pymysql
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from app.application.errores import IntegracionNoConfigurada
from app.core.config import PROJECT_ROOT, Settings
from app.domain.consulta import Diagnostico, NuevaConsulta, Receta, Tratamiento
from app.domain.errores import (
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
)
from app.domain.paciente import Alergia, Baja, Contacto, MotivoBaja, NuevoPaciente
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
    for archivo in ("003_permisos.sql", "005_permisos_escritura.sql"):
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
                "UPDATE paciente SET nombre = 'Otro'",
                "UPDATE consulta_medica SET motivo_consulta = 'Otro'",
                "SELECT salario FROM medico",
                "INSERT INTO medico (nombre, apellido, colegiado) VALUES ('a','b','c')",
                "SELECT * FROM facturacion",
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
