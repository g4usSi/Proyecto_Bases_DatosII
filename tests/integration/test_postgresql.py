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
from app.domain.cita import EstadoCita, NuevaCita
from app.domain.consulta import Adenda, Diagnostico, NuevaConsulta, Receta, Tratamiento
from app.domain.errores import (
    CitaNoEncontrada,
    ConflictoAgenda,
    ConsultaNoEncontrada,
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
)
from app.domain.paciente import (
    Alergia,
    Baja,
    CambiosPaciente,
    Contacto,
    MotivoBaja,
    NuevoPaciente,
)
from app.infrastructure.persistence.postgresql.unidad import UnidadTrabajoPostgreSQL
from app.main import create_app
from scripts.sincronizar_profesionales import sincronizar_hospital

PERMISOS = [
    "pacientes:leer",
    "pacientes:registrar",
    "historiales:leer",
    "consultas:registrar",
    "historiales:archivar",
    "citas:leer",
    "citas:gestionar",
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
        ("cita", "DELETE FROM cita WHERE id_paciente = ANY(%s)"),
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


# ---------------------------------------------------------------------------------------
# Adendas, correccion de datos, citas y reglas de integridad (migraciones 009 y 010)
# ---------------------------------------------------------------------------------------


def consulta_base(hospital, identificador) -> str:
    with hospital.unidad() as unidad:
        creada = unidad.historial.registrar_consulta(
            identificador,
            hospital.profesional,
            NuevaConsulta(
                "Dolor de cabeza",
                notas="Primera visita",
                diagnosticos=(Diagnostico("Cefalea"),),
            ),
        )
        unidad.commit()
    return creada.id_consulta


def test_adenda_agrega_diagnostico_tratamiento_receta_y_nota(hospital):
    identificador = registrar(hospital)
    id_consulta = consulta_base(hospital, identificador)
    adenda = Adenda(
        nota="Resultado de laboratorio recibido",
        diagnosticos=(Diagnostico("Migrana", "G43", "CIE-10"),),
        tratamientos=(Tratamiento("Evitar luz intensa"),),
        recetas=(Receta("Sumatriptan", "50 mg", "una vez"),),
    )
    with hospital.unidad() as unidad:
        actualizada = unidad.historial.agregar_a_consulta(
            identificador, id_consulta, hospital.profesional, adenda
        )
        unidad.commit()
    with hospital.unidad() as unidad:
        leida = unidad.historial.obtener_consulta(identificador, id_consulta)
    assert leida == actualizada
    assert [d.descripcion for d in leida.diagnosticos] == ["Cefalea", "Migrana"]
    assert [t.descripcion for t in leida.tratamientos] == ["Evitar luz intensa"]
    assert [r.medicamento for r in leida.recetas] == ["Sumatriptan"]
    assert leida.notas.startswith("Primera visita\n\n[Adenda ")
    assert hospital.profesional in leida.notas and "Resultado de laboratorio" in leida.notas
    assert "1 diagnostico, 1 tratamiento, 1 receta" in leida.notas


def test_adenda_solo_con_nota_y_tratamiento_bajo_diagnostico_existente(hospital):
    identificador = registrar(hospital)
    id_consulta = consulta_base(hospital, identificador)
    with hospital.unidad() as unidad:
        unidad.historial.agregar_a_consulta(
            identificador,
            id_consulta,
            hospital.profesional,
            Adenda(tratamientos=(Tratamiento("Hidratacion"),)),
        )
        unidad.historial.agregar_a_consulta(
            identificador, id_consulta, hospital.profesional, Adenda(nota="Aclaracion")
        )
        unidad.commit()
    with hospital.unidad() as unidad:
        leida = unidad.historial.obtener_consulta(identificador, id_consulta)
    assert [t.descripcion for t in leida.tratamientos] == ["Hidratacion"]
    assert leida.notas.count("[Adenda ") == 2


def test_adenda_no_deja_nada_sin_commit_ni_en_consultas_ajenas(hospital):
    identificador, otro = registrar(hospital), registrar(hospital, "Otro")
    id_consulta = consulta_base(hospital, identificador)
    with hospital.unidad() as unidad:
        unidad.historial.agregar_a_consulta(
            identificador, id_consulta, hospital.profesional, Adenda(nota="No se confirma")
        )
    with hospital.unidad() as unidad:
        assert unidad.historial.obtener_consulta(identificador, id_consulta).notas == (
            "Primera visita"
        )
        # La consulta es de otro paciente (o no existe): no se puede agregar.
        for id_malo in (id_consulta, "999999999", "abc"):
            with pytest.raises(ConsultaNoEncontrada):
                unidad.historial.agregar_a_consulta(
                    otro, id_malo, hospital.profesional, Adenda(nota="x")
                )
        assert unidad.historial.obtener_consulta(otro, id_consulta) is None


def test_adenda_tratamiento_sin_ningun_diagnostico_es_invalido(hospital):
    identificador = registrar(hospital)
    with hospital.unidad() as unidad:
        creada = unidad.historial.registrar_consulta(
            identificador, hospital.profesional, NuevaConsulta("Chequeo")
        )
        unidad.commit()
    with hospital.unidad() as unidad, pytest.raises(DatosInvalidos):
        unidad.historial.agregar_a_consulta(
            identificador,
            creada.id_consulta,
            hospital.profesional,
            Adenda(tratamientos=(Tratamiento("X"),)),
        )


def test_adenda_en_historial_archivado_se_rechaza_y_la_base_lo_refuerza(hospital, admin):
    identificador = registrar(hospital)
    id_consulta = consulta_base(hospital, identificador)
    with hospital.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.ADMINISTRATIVO, hospital.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with hospital.unidad() as unidad, pytest.raises(PacienteArchivado):
        unidad.historial.agregar_a_consulta(
            identificador, id_consulta, hospital.profesional, Adenda(nota="x")
        )
    # Aunque alguien se salte la API, la base tampoco acepta diagnosticos nuevos.
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute(
            "INSERT INTO diagnostico (id_atencion, descripcion) VALUES (%s, 'x')",
            (int(id_consulta),),
        )


def test_la_base_no_deja_reescribir_notas_ni_la_identidad_de_una_consulta(hospital, admin):
    identificador = registrar(hospital)
    id_consulta = int(consulta_base(hospital, identificador))
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute(
            "UPDATE atencion SET notas = 'otra cosa' WHERE id_atencion = %s", (id_consulta,)
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        admin.execute(
            "UPDATE atencion SET motivo = 'cambiado' WHERE id_atencion = %s", (id_consulta,)
        )
    admin.execute(
        "UPDATE atencion SET notas = notas || ' (anexo)' WHERE id_atencion = %s", (id_consulta,)
    )


def test_corregir_datos_del_paciente_y_agregar_alergias(hospital):
    identificador = registrar(hospital, contacto=Contacto(telefono="111"))
    with hospital.unidad() as unidad:
        unidad.pacientes.actualizar(
            identificador,
            CambiosPaciente(
                nombres="Ana Maria",
                fecha_nacimiento=date(1991, 6, 2),
                contacto=Contacto(correo="nuevo@example.invalid"),
            ),
        )
        unidad.pacientes.agregar_alergias(identificador, (Alergia("Polen", "Estornudos"),))
        unidad.commit()
    with hospital.unidad() as unidad:
        p = unidad.pacientes.obtener_por_id(identificador)
        assert (p.nombres, p.apellidos, p.fecha_nacimiento) == (
            "Ana Maria",
            hospital.marca,
            date(1991, 6, 2),
        )
        assert p.contacto == Contacto(None, "nuevo@example.invalid", None)  # reemplazo total
        assert p.alergias == (Alergia("Polen", "Estornudos"),)
        with pytest.raises(DatosInvalidos):  # ya registrada
            unidad.pacientes.agregar_alergias(identificador, (Alergia("Polen"),))
    with hospital.unidad() as unidad, pytest.raises(DatosInvalidos):
        unidad.pacientes.actualizar(
            identificador, CambiosPaciente(fecha_nacimiento=date.today() + timedelta(days=2))
        )
    with hospital.unidad() as unidad, pytest.raises(PacienteNoEncontrado):
        unidad.pacientes.actualizar("999999999", CambiosPaciente(nombres="X"))


def test_no_se_corrigen_datos_de_un_historial_archivado(hospital):
    identificador = registrar(hospital)
    with hospital.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.TRASLADO, hospital.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with hospital.unidad() as unidad:
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.actualizar(identificador, CambiosPaciente(nombres="Nuevo"))
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.agregar_alergias(identificador, (Alergia("Polen"),))


def manana(horas=9) -> datetime:
    """Una fecha futura con hora UTC redonda."""
    base = datetime.now(UTC) + timedelta(days=3)
    return base.replace(hour=horas, minute=0, second=0, microsecond=0)


def nueva_cita(hospital, paciente, inicio, minutos=30) -> NuevaCita:
    return NuevaCita(paciente, hospital.profesional, inicio, minutos, "Control")


def test_profesional_local_visible_para_la_agenda(hospital):
    with hospital.unidad() as unidad:
        perfil = unidad.profesionales.obtener(hospital.profesional)
        assert unidad.profesionales.obtener(str(uuid4())) is None
        assert unidad.profesionales.obtener("no-es-uuid") is None
    assert perfil.id_profesional == hospital.profesional
    assert perfil.rol == "medico" and perfil.activo and perfil.atiende_pacientes


def test_cita_ida_y_vuelta_en_hora_local_y_utc(hospital, admin):
    identificador = registrar(hospital)
    inicio = manana(15)  # 15:00 UTC = 09:00 en Guatemala (UTC-6)
    with hospital.unidad() as unidad:
        cita = unidad.citas.agendar(
            nueva_cita(hospital, identificador, inicio, 45),
            "Ana Prueba",
            hospital.profesional,
        )
        unidad.commit()
    assert cita.estado == EstadoCita.PROGRAMADA
    assert cita.inicio == inicio and cita.fin == inicio + timedelta(minutes=45)
    assert cita.nombre_paciente == f"Ana {hospital.marca}"
    assert cita.id_profesional == hospital.profesional
    assert cita.creada_por == hospital.profesional
    fila = admin.execute(
        "SELECT fecha, hora FROM cita WHERE id_cita = %s", (int(cita.id_cita),)
    ).fetchone()
    assert fila[1].hour == 9  # la base guarda la hora local del hospital
    with hospital.unidad() as unidad:
        assert unidad.citas.obtener(cita.id_cita) == cita
        agenda = unidad.citas.listar_agenda(
            inicio - timedelta(hours=1), inicio + timedelta(hours=1), hospital.profesional
        )
        assert agenda == [cita]
        assert (
            unidad.citas.listar_agenda(inicio + timedelta(hours=1), inicio + timedelta(hours=2))
            == []
        )
        assert unidad.citas.listar_agenda(inicio, inicio + timedelta(hours=1), str(uuid4())) == []
        assert unidad.citas.listar_por_paciente(identificador, 10) == [cita]
        assert unidad.citas.obtener("999999999") is None


def test_citas_que_se_cruzan_chocan_y_cancelar_libera_el_horario(hospital):
    a, b = registrar(hospital), registrar(hospital, "Beto")
    inicio = manana()
    with hospital.unidad() as unidad:
        primera = unidad.citas.agendar(nueva_cita(hospital, a, inicio), "A", hospital.profesional)
        unidad.commit()
    with hospital.unidad() as unidad:
        # Se cruza (empieza a mitad de la primera) -> 409
        with pytest.raises(ConflictoAgenda):
            unidad.citas.agendar(
                nueva_cita(hospital, b, inicio + timedelta(minutes=10)), "B", hospital.profesional
            )
    with hospital.unidad() as unidad:
        # Justo al terminar la primera: no se cruza
        unidad.citas.agendar(
            nueva_cita(hospital, b, inicio + timedelta(minutes=30)), "B", hospital.profesional
        )
        unidad.commit()
    with hospital.unidad() as unidad:
        cancelada = unidad.citas.cambiar_estado(
            primera.id_cita, EstadoCita.CANCELADA, hospital.profesional, "Paciente avisa"
        )
        unidad.commit()
    assert cancelada.estado == EstadoCita.CANCELADA and cancelada.motivo_cambio == "Paciente avisa"
    with hospital.unidad() as unidad:
        unidad.citas.agendar(nueva_cita(hospital, b, inicio), "B", hospital.profesional)
        unidad.commit()


def test_estados_de_cita_y_transiciones(hospital):
    identificador = registrar(hospital)
    with hospital.unidad() as unidad:
        cita = unidad.citas.agendar(
            nueva_cita(hospital, identificador, manana()), "A", hospital.profesional
        )
        unidad.commit()
    with hospital.unidad() as unidad:
        confirmada = unidad.citas.cambiar_estado(
            cita.id_cita, EstadoCita.CONFIRMADA, hospital.profesional, None
        )
        unidad.commit()
        assert confirmada.estado == EstadoCita.CONFIRMADA
    with hospital.unidad() as unidad, pytest.raises(ConflictoAgenda):
        # Una cita confirmada sigue ocupando el horario.
        unidad.citas.agendar(
            nueva_cita(hospital, identificador, manana()), "A", hospital.profesional
        )
    with hospital.unidad() as unidad:
        unidad.citas.cambiar_estado(cita.id_cita, EstadoCita.NO_ASISTIO, hospital.profesional, None)
        unidad.commit()
    with hospital.unidad() as unidad:
        with pytest.raises(ConflictoAgenda):  # final: ya no cambia
            unidad.citas.cambiar_estado(
                cita.id_cita, EstadoCita.CANCELADA, hospital.profesional, "x"
            )
        with pytest.raises(CitaNoEncontrada):
            unidad.citas.cambiar_estado(
                "999999999", EstadoCita.CANCELADA, hospital.profesional, "x"
            )


def test_cita_a_historial_archivado_o_profesional_inexistente(hospital):
    identificador = registrar(hospital)
    with hospital.unidad() as unidad, pytest.raises(DatosInvalidos):
        unidad.citas.agendar(
            NuevaCita(identificador, str(uuid4()), manana(), 30, "x"), "A", hospital.profesional
        )
    with hospital.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.TRASLADO, hospital.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with hospital.unidad() as unidad, pytest.raises(PacienteArchivado):
        unidad.citas.agendar(
            nueva_cita(hospital, identificador, manana()), "A", hospital.profesional
        )


def test_dos_secretarias_reservando_el_mismo_horario_solo_una_gana(hospital):
    a, b = registrar(hospital), registrar(hospital, "Beto")
    inicio = manana(18)
    resultados = []
    barrera = threading.Barrier(2)

    def reservar(paciente):
        try:
            with hospital.unidad() as unidad:
                barrera.wait(timeout=10)
                unidad.citas.agendar(
                    nueva_cita(hospital, paciente, inicio), "X", hospital.profesional
                )
                unidad.commit()
            resultados.append("ok")
        except ConflictoAgenda:
            resultados.append("choque")

    hilos = [threading.Thread(target=reservar, args=(p,)) for p in (a, b)]
    [h.start() for h in hilos]
    [h.join(timeout=20) for h in hilos]
    assert sorted(resultados) == ["choque", "ok"]


def test_la_api_solo_ve_lo_necesario_del_personal(hospital):
    with hospital.unidad() as unidad:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            unidad.conexion.execute("SELECT colegiado, correo FROM personal_medico").fetchall()


# ---- Reglas de integridad del Hospital General (010_integridad_hospital.sql) ----------


@pytest.fixture
def tx(admin, hospital):
    """Una transaccion que siempre se revierte: las pruebas de reglas no dejan datos."""
    admin.autocommit = False
    try:
        yield admin
    finally:
        admin.rollback()
        admin.autocommit = True


def _cobro(tx, hospital, total=200, abierto=True):
    paciente = int(registrar_en(tx, hospital.marca))
    personal = tx.execute(
        "SELECT id_personal FROM personal_medico WHERE id_profesional_central = %s",
        (hospital.profesional,),
    ).fetchone()[0]
    servicio = tx.execute(
        "INSERT INTO servicio (nombre, tipo, unidad_cobro) VALUES ('s', 'Consulta', 'Por_evento') "
        "RETURNING id_servicio"
    ).fetchone()[0]
    tarifa = tx.execute(
        "INSERT INTO tarifa (id_servicio, monto_vigente) VALUES (%s, 100) RETURNING id_tarifa",
        (servicio,),
    ).fetchone()[0]
    atencion = tx.execute(
        "INSERT INTO atencion (id_paciente, id_personal, tipo_atencion) "
        "VALUES (%s, %s, 'CONSULTA') RETURNING id_atencion",
        (paciente, personal),
    ).fetchone()[0]
    cobro = tx.execute(
        "INSERT INTO cobro (id_atencion) VALUES (%s) RETURNING id_cobro", (atencion,)
    ).fetchone()[0]
    tx.execute(
        "INSERT INTO detalle_cobro (id_cobro, id_tarifa, cantidad, precio_unitario_aplicado) "
        "VALUES (%s, %s, %s, 100)",
        (cobro, tarifa, total // 100),
    )
    return paciente, personal, atencion, cobro, tarifa


def registrar_en(conexion, marca) -> str:
    return str(
        conexion.execute(
            "INSERT INTO paciente (nombres, apellidos) VALUES ('Regla', %s) RETURNING id_paciente",
            (marca,),
        ).fetchone()[0]
    )


def intentar(tx, sql, parametros=()):
    """Ejecuta dentro de un savepoint para poder seguir usando la transaccion tras un error."""
    with tx.transaction():
        return tx.execute(sql, parametros)


def test_pagos_no_pueden_exceder_el_total_ni_editarse(tx, hospital):
    _, _, _, cobro, _ = _cobro(tx, hospital, 200)
    pago = tx.execute(
        "INSERT INTO pago (id_cobro, id_metodo_pago, monto) VALUES (%s, 1, 150) RETURNING id_pago",
        (cobro,),
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.CheckViolation):  # 150 + 60 > 200
        intentar(
            tx, "INSERT INTO pago (id_cobro, id_metodo_pago, monto) VALUES (%s, 1, 60)", (cobro,)
        )
    with pytest.raises(psycopg.errors.CheckViolation):  # un pago no se edita
        intentar(tx, "UPDATE pago SET monto = 10 WHERE id_pago = %s", (pago,))
    intentar(tx, "UPDATE pago SET estado = 'Anulado' WHERE id_pago = %s", (pago,))
    with pytest.raises(psycopg.errors.CheckViolation):  # un anulado no se reactiva
        intentar(tx, "UPDATE pago SET estado = 'Confirmado' WHERE id_pago = %s", (pago,))
    # Anulado el primero, vuelve a haber saldo.
    intentar(tx, "INSERT INTO pago (id_cobro, id_metodo_pago, monto) VALUES (%s, 1, 200)", (cobro,))


def test_el_total_del_cobro_no_baja_de_lo_pagado_y_los_cargos_se_congelan(tx, hospital):
    _, _, _, cobro, tarifa = _cobro(tx, hospital, 200)
    tx.execute("INSERT INTO pago (id_cobro, id_metodo_pago, monto) VALUES (%s, 1, 150)", (cobro,))
    with pytest.raises(psycopg.errors.CheckViolation):
        intentar(tx, "DELETE FROM detalle_cobro WHERE id_cobro = %s", (cobro,))
    with pytest.raises(psycopg.errors.CheckViolation):
        intentar(tx, "UPDATE detalle_cobro SET cantidad = 1 WHERE id_cobro = %s", (cobro,))
    # Subir el cargo si esta permitido mientras el cobro este Abierto.
    intentar(tx, "UPDATE detalle_cobro SET cantidad = 3 WHERE id_cobro = %s", (cobro,))
    # Un cobro Pagado o Cerrado ya no admite cargos.
    tx.execute("UPDATE cobro SET estado = 'Cerrado' WHERE id_cobro = %s", (cobro,))
    with pytest.raises(psycopg.errors.CheckViolation):
        intentar(
            tx,
            "INSERT INTO detalle_cobro (id_cobro, id_tarifa, cantidad, precio_unitario_aplicado) "
            "VALUES (%s, %s, 1, 100)",
            (cobro, tarifa),
        )


def test_estados_del_cobro(tx, hospital):
    _, _, _, cobro, _ = _cobro(tx, hospital, 200)
    with pytest.raises(psycopg.errors.CheckViolation):  # no esta saldado
        intentar(tx, "UPDATE cobro SET estado = 'Pagado' WHERE id_cobro = %s", (cobro,))
    tx.execute("INSERT INTO pago (id_cobro, id_metodo_pago, monto) VALUES (%s, 1, 200)", (cobro,))
    with pytest.raises(psycopg.errors.CheckViolation):  # tiene pagos confirmados
        intentar(tx, "UPDATE cobro SET estado = 'Anulado' WHERE id_cobro = %s", (cobro,))
    tx.execute("UPDATE cobro SET estado = 'Pagado' WHERE id_cobro = %s", (cobro,))
    with pytest.raises(psycopg.errors.CheckViolation):  # final
        intentar(tx, "UPDATE cobro SET estado = 'Abierto' WHERE id_cobro = %s", (cobro,))


def test_una_cama_no_tiene_dos_ingresos_a_la_vez_ni_un_paciente_dos_camas(tx, hospital):
    paciente, personal, _, _, _ = _cobro(tx, hospital)
    otro = int(registrar_en(tx, hospital.marca))
    depto = tx.execute(
        "INSERT INTO departamento (descripcion) VALUES ('d') RETURNING id_departamento"
    ).fetchone()[0]
    hab = tx.execute(
        "INSERT INTO habitacion (id_departamento, numero) VALUES (%s, '1') RETURNING id_habitacion",
        (depto,),
    ).fetchone()[0]
    camas = [
        tx.execute(
            "INSERT INTO cama (id_habitacion, codigo, estado_operativo) "
            "VALUES (%s, %s, 'Disponible') RETURNING id_cama",
            (hab, f"C{n}"),
        ).fetchone()[0]
        for n in (1, 2)
    ]

    def ingreso(id_paciente, cama, desde, hasta=None):
        atencion = tx.execute(
            "INSERT INTO atencion (id_paciente, id_personal, tipo_atencion) "
            "VALUES (%s, %s, 'INGRESO') RETURNING id_atencion",
            (id_paciente, personal),
        ).fetchone()[0]
        return intentar(
            tx,
            "INSERT INTO ingreso (id_atencion, id_cama, fecha_hora_ingreso, tipo, fecha_hora_alta) "
            "VALUES (%s, %s, %s, 'Programado', %s)",
            (atencion, cama, desde, hasta),
        )

    t0 = datetime(2026, 1, 1, 8, 0)
    ingreso(paciente, camas[0], t0, t0 + timedelta(days=2))
    with pytest.raises(psycopg.errors.ExclusionViolation):  # misma cama, se solapa
        ingreso(otro, camas[0], t0 + timedelta(days=1))
    ingreso(otro, camas[0], t0 + timedelta(days=2))  # justo despues del alta: libre
    with pytest.raises(psycopg.errors.CheckViolation):  # el paciente ya esta ingresado
        ingreso(paciente, camas[1], t0 + timedelta(hours=5))


def test_la_atencion_de_una_cita_debe_ser_del_mismo_paciente(tx, hospital):
    paciente, personal, _, _, _ = _cobro(tx, hospital)
    otro = int(registrar_en(tx, hospital.marca))
    cita = tx.execute(
        "INSERT INTO cita (id_paciente, id_personal, fecha, hora) "
        "VALUES (%s, %s, current_date + 5, '10:00') RETURNING id_cita",
        (paciente, personal),
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        intentar(
            tx,
            "INSERT INTO atencion (id_paciente, id_personal, id_cita, tipo_atencion) "
            "VALUES (%s, %s, %s, 'CONSULTA')",
            (otro, personal, cita),
        )
    intentar(
        tx,
        "INSERT INTO atencion (id_paciente, id_personal, id_cita, tipo_atencion) "
        "VALUES (%s, %s, %s, 'CONSULTA')",
        (paciente, personal, cita),
    )


def test_flujo_de_adenda_correccion_y_citas_por_la_api(hospital):
    with TestClient(create_app(Settings())) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": hospital.correo, "password": hospital.password}
        )
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        pid = client.post(
            "/api/v1/pacientes",
            json={"nombres": "Rosa", "apellidos": hospital.marca},
            headers=h,
        ).json()["id_paciente"]
        consulta = client.post(
            f"/api/v1/pacientes/{pid}/consultas",
            json={"motivo": "Fiebre", "diagnosticos": [{"descripcion": "Viral"}]},
            headers=h,
        ).json()
        ruta = f"/api/v1/pacientes/{pid}/consultas/{consulta['id_consulta']}"
        vacia = client.post(ruta + "/adenda", json={}, headers=h)
        assert vacia.status_code == 422
        agregada = client.post(
            ruta + "/adenda",
            json={
                "nota": "Cultivo negativo",
                "recetas": [
                    {"medicamento": "Paracetamol", "dosis": "500 mg", "frecuencia": "c/8h"}
                ],
            },
            headers=h,
        )
        assert agregada.status_code == 200
        assert agregada.json()["recetas"][0]["medicamento"] == "Paracetamol"
        assert "Cultivo negativo" in agregada.json()["notas"]
        assert client.get(ruta, headers=h).json() == agregada.json()
        assert client.get(f"/api/v1/pacientes/{pid}/consultas/999999", headers=h).status_code == 404

        corregido = client.patch(
            f"/api/v1/pacientes/{pid}",
            json={"apellidos": hospital.marca + "x", "contacto": {"telefono": "7777"}},
            headers=h,
        )
        assert corregido.status_code == 200 and corregido.json()["contacto"]["telefono"] == "7777"
        assert client.patch(f"/api/v1/pacientes/{pid}", json={}, headers=h).status_code == 422
        alergias = client.post(
            f"/api/v1/pacientes/{pid}/alergias",
            json={"alergias": [{"sustancia": "Latex"}]},
            headers=h,
        )
        assert (
            alergias.status_code == 200 and alergias.json()["alergias"][0]["sustancia"] == "Latex"
        )
        repetida = client.post(
            f"/api/v1/pacientes/{pid}/alergias",
            json={"alergias": [{"sustancia": "latex"}]},
            headers=h,
        )
        assert repetida.status_code == 422

        inicio = manana(16).isoformat()
        cita = client.post(
            "/api/v1/citas",
            json={
                "id_paciente": pid,
                "id_profesional": hospital.profesional,
                "inicio": inicio,
                "duracion_minutos": 30,
                "motivo": "Control",
            },
            headers=h,
        )
        assert cita.status_code == 201, cita.text
        assert cita.json()["estado"] == "programada" and cita.json()["fin"] is not None
        choque = client.post(
            "/api/v1/citas",
            json={
                "id_paciente": pid,
                "id_profesional": hospital.profesional,
                "inicio": inicio,
                "duracion_minutos": 15,
                "motivo": "Otro",
            },
            headers=h,
        )
        assert choque.status_code == 409
        agenda = client.get(
            "/api/v1/citas",
            params={"desde": manana(0).isoformat(), "hasta": manana(23).isoformat()},
            headers=h,
        )
        assert [c["id_cita"] for c in agenda.json()] == [cita.json()["id_cita"]]
        assert client.get(f"/api/v1/pacientes/{pid}/citas", headers=h).json() == agenda.json()
        cancelada = client.post(
            f"/api/v1/citas/{cita.json()['id_cita']}/estado",
            json={"estado": "cancelada", "motivo": "Se reprograma"},
            headers=h,
        )
        assert cancelada.status_code == 200 and cancelada.json()["estado"] == "cancelada"
        sin_motivo = client.post(
            f"/api/v1/citas/{cita.json()['id_cita']}/estado",
            json={"estado": "cancelada"},
            headers=h,
        )
        assert sin_motivo.status_code == 422
