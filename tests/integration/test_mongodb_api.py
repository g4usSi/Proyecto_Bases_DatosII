"""Laboratorio Clinico (MongoDB) con datos sinteticos; se borran al terminar.

Usa la misma cuenta limitada que la API (historiales_app) y la cuenta administrativa solo
para preparar y limpiar. Requiere la base inicializada con laboratorio_clinico_mongo.js.
"""

import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pymongo import MongoClient

from app.core.config import Settings
from app.domain.consulta import Diagnostico, NuevaConsulta, Receta, Tratamiento
from app.domain.errores import (
    DatosInvalidos,
    PacienteArchivado,
    PacienteNoEncontrado,
    ProfesionalNoVinculado,
)
from app.domain.paciente import Alergia, Baja, Contacto, MotivoBaja, NuevoPaciente
from app.infrastructure.persistence.mongodb.unidad import UnidadTrabajoMongo
from app.main import create_app
from scripts.sincronizar_profesionales import sincronizar_laboratorio

PERMISOS = [
    "pacientes:leer",
    "pacientes:registrar",
    "historiales:leer",
    "consultas:registrar",
    "historiales:archivar",
]


@pytest.fixture(scope="module")
def clientes(config_local):
    admin = MongoClient(
        host="127.0.0.1",
        port=int(config_local["MONGO_PORT"]),
        username="historiales_admin",
        password=config_local["MONGO_ROOT_PASSWORD"],
        authSource="admin",
    )
    app = MongoClient(config_local["HISTORIALES_MONGODB_URI"])
    yield admin.laboratorio_clinico, app.laboratorio_clinico
    admin.close()
    app.close()


@pytest.fixture
def admin_pg(config_local):
    conexion = psycopg.connect(config_local["HISTORIALES_POSTGRES_ADMIN_DSN"], autocommit=True)
    yield conexion
    conexion.close()


@pytest.fixture
def lab(config_local, clientes, admin_pg):
    """Un profesional del Laboratorio Clinico y una marca para identificar sus pacientes."""
    admin, app = clientes
    marca = "Zzprueba" + uuid4().hex[:10]
    profesional = uuid4()
    correo = f"lab-{profesional}@example.invalid"
    password = "Contrasena sintetica de prueba"
    admin_pg.execute(
        "INSERT INTO identidad.profesional "
        "(id_profesional,correo,nombres,apellidos,password_hash,establecimiento,rol) "
        "VALUES (%s,%s,'Prueba','Laboratorista',%s,'laboratorio_clinico','medico')",
        (profesional, correo, PasswordHash.recommended().hash(password)),
    )
    for permiso in PERMISOS:
        admin_pg.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s,%s)", (profesional, permiso)
        )
    sincronizar_laboratorio(
        config_local["HISTORIALES_POSTGRES_ADMIN_DSN"], [str(profesional)], admin.profesionales
    )

    class Entorno:
        pass

    entorno = Entorno()
    entorno.marca = marca
    entorno.profesional = str(profesional)
    entorno.correo = correo
    entorno.password = password
    entorno.admin = admin
    entorno.unidad = lambda: UnidadTrabajoMongo(app)
    yield entorno

    ids = [
        p["_id"] for p in admin.pacientes.find({"apellidos": {"$regex": f"^{marca}"}}, {"_id": 1})
    ]
    admin.consultas.delete_many({"id_paciente": {"$in": ids}})
    admin.pacientes.delete_many({"_id": {"$in": ids}})
    admin.profesionales.delete_many({"id_profesional_central": str(profesional)})
    admin_pg.execute("DELETE FROM identidad.profesional WHERE id_profesional = %s", (profesional,))


def registrar(lab, nombres="Ana", **extra) -> str:
    with lab.unidad() as unidad:
        paciente = unidad.pacientes.registrar(NuevoPaciente(nombres, lab.marca, **extra))
        unidad.commit()
    return paciente.id_paciente


def test_registrar_leer_con_contacto_y_alergias(lab):
    identificador = registrar(
        lab,
        fecha_nacimiento=datetime(1990, 5, 1).date(),
        contacto=Contacto(telefono="5555-0000", correo="a@example.invalid"),
        alergias=(Alergia("Penicilina", "Urticaria", "grave"), Alergia("Latex", reaccion="  ")),
    )
    with lab.unidad() as unidad:
        paciente = unidad.pacientes.obtener_por_id(identificador)
    assert paciente.fecha_nacimiento == datetime(1990, 5, 1).date()
    assert paciente.contacto == Contacto("5555-0000", "a@example.invalid", None)
    assert paciente.alergias == (Alergia("Penicilina", "Urticaria", "grave"), Alergia("Latex"))
    assert paciente.archivado is False
    documento = lab.admin.pacientes.find_one({"_id": ObjectId(identificador)})
    assert documento["numero_expediente"].startswith("LAB-")
    assert "reaccion" not in documento["alergias"][1]  # el vacio se omite, no se guarda


def test_fecha_nacimiento_y_contacto_son_opcionales(lab):
    identificador = registrar(lab, "Minima")
    with lab.unidad() as unidad:
        paciente = unidad.pacientes.obtener_por_id(identificador)
    assert paciente.fecha_nacimiento is None and paciente.contacto is None
    assert paciente.alergias is None


def test_alergias_no_evaluadas_y_evaluadas_sin_alergias_son_distintas(lab):
    sin_evaluar = registrar(lab, "Sin")
    sin_alergias = registrar(lab, "Cero", alergias=())
    with lab.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(sin_evaluar).alergias is None
        assert unidad.pacientes.obtener_por_id(sin_alergias).alergias == ()


def test_sin_commit_o_con_rollback_no_se_guarda_nada(lab):
    with lab.unidad() as unidad:
        fantasma = unidad.pacientes.registrar(NuevoPaciente("Fantasma", lab.marca))
    with lab.unidad() as unidad:
        descartado = unidad.pacientes.registrar(NuevoPaciente("Descartado", lab.marca))
        unidad.rollback()
        unidad.commit()
    with lab.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(fantasma.id_paciente) is None
        assert unidad.pacientes.obtener_por_id(descartado.id_paciente) is None


@pytest.mark.parametrize(
    "identificador", ["0", "abc", "1; drop", "x" * 24, "12345678901234567890123"]
)
def test_identificadores_invalidos_no_existen(lab, identificador):
    with lab.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(identificador) is None
        assert unidad.historial.listar_consultas(identificador, 5) == []


def test_busqueda_por_nombre_regla_comun(lab):
    maria = registrar(lab, "María José")
    marco = registrar(lab, "Marco")
    nino = registrar(lab, "Ñandú")
    marca = lab.marca.lower()
    with lab.unidad() as unidad:
        buscar = unidad.pacientes.buscar
        assert {p.id_paciente for p in buscar(("mar", marca), 10)} == {maria, marco}
        assert [p.id_paciente for p in buscar(("jose", marca), 10)] == [maria]
        assert [p.id_paciente for p in buscar(("nandu", marca), 10)] == [nino]
        assert [p.id_paciente for p in buscar(("maría", marca), 10)] == [maria]
        assert buscar(("zzz", marca), 10) == []
        assert len(buscar((marca,), 1)) == 1
        # Mitad de una palabra no cuenta: solo comienzos.
        assert buscar(("aria", marca), 10) == []
        # Los caracteres de regex se tratan como texto, no como patron.
        for peligroso in (".", ".*", "(", "[a-z]", "a|b", "\\", "^", "$"):
            assert buscar((peligroso,), 10) == [], peligroso


def test_busqueda_orden_e_incluye_archivados(lab):
    primero = registrar(lab, "Berta")
    segundo = registrar(lab, "Alba")
    baja = Baja(MotivoBaja.ADMINISTRATIVO, lab.profesional, datetime.now(UTC))
    with lab.unidad() as unidad:
        unidad.pacientes.archivar(primero, baja)
        unidad.commit()
    with lab.unidad() as unidad:
        encontrados = unidad.pacientes.buscar((lab.marca.lower(),), 10)
    assert [p.id_paciente for p in encontrados] == [segundo, primero]
    assert [p.archivado for p in encontrados] == [False, True]


def test_consulta_completa_en_un_documento_y_leida_igual(lab):
    identificador = registrar(lab)
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
    with lab.unidad() as unidad:
        creada = unidad.historial.registrar_consulta(identificador, lab.profesional, nueva)
        unidad.commit()
    with lab.unidad() as unidad:
        [leida] = unidad.historial.listar_consultas(identificador, 10)
    assert leida.id_consulta == creada.id_consulta
    assert leida.fecha_hora == creada.fecha_hora  # mismo valor: Mongo guarda milisegundos
    assert leida.id_profesional == lab.profesional
    assert leida.motivo == "Dolor abdominal" and leida.notas == "Sin fiebre"
    assert leida.diagnosticos == nueva.diagnosticos
    assert leida.tratamientos == nueva.tratamientos
    assert leida.recetas == nueva.recetas
    assert abs(leida.fecha_hora - datetime.now(UTC)) < timedelta(minutes=1)
    assert lab.admin.consultas.count_documents({"id_paciente": ObjectId(identificador)}) == 1


def test_consulta_sin_commit_no_se_guarda(lab):
    identificador = registrar(lab)
    with lab.unidad() as unidad:
        unidad.historial.registrar_consulta(identificador, lab.profesional, NuevaConsulta("X"))
    with lab.unidad() as unidad:
        assert unidad.historial.listar_consultas(identificador, 10) == []


def test_documento_invalido_se_rechaza_sin_guardar_nada(lab):
    identificador = registrar(lab)
    mala = NuevaConsulta("Control", recetas=(Receta("X", "1", "1", duracion_dias=0),))
    with pytest.raises(DatosInvalidos):
        with lab.unidad() as unidad:
            unidad.historial.registrar_consulta(identificador, lab.profesional, mala)
            unidad.commit()
    assert lab.admin.consultas.count_documents({"id_paciente": ObjectId(identificador)}) == 0


def test_profesional_sin_vinculo_o_inactivo_no_puede_registrar(lab):
    identificador = registrar(lab)
    with lab.unidad() as unidad, pytest.raises(ProfesionalNoVinculado):
        unidad.historial.registrar_consulta(identificador, str(uuid4()), NuevaConsulta("X"))
    with lab.unidad() as unidad, pytest.raises(ProfesionalNoVinculado):
        unidad.historial.registrar_consulta(identificador, "no-es-uuid", NuevaConsulta("X"))
    lab.admin.profesionales.update_one(
        {"id_profesional_central": lab.profesional}, {"$set": {"activo": False}}
    )
    with lab.unidad() as unidad, pytest.raises(ProfesionalNoVinculado):
        unidad.historial.registrar_consulta(identificador, lab.profesional, NuevaConsulta("X"))


def test_paciente_inexistente(lab):
    with lab.unidad() as unidad, pytest.raises(PacienteNoEncontrado):
        unidad.historial.registrar_consulta(str(ObjectId()), lab.profesional, NuevaConsulta("X"))


def test_paginacion_por_cursor(lab):
    identificador = registrar(lab)
    for i in range(5):
        with lab.unidad() as unidad:
            unidad.historial.registrar_consulta(
                identificador, lab.profesional, NuevaConsulta(f"Consulta {i}")
            )
            unidad.commit()
    with lab.unidad() as unidad:
        primera = unidad.historial.listar_consultas(identificador, 3)
        segunda = unidad.historial.listar_consultas(identificador, 3, primera[-1].fecha_hora)
    assert [c.motivo for c in primera] == ["Consulta 4", "Consulta 3", "Consulta 2"]
    assert [c.motivo for c in segunda] == ["Consulta 1", "Consulta 0"]


def test_archivar_es_condicional_y_bloquea_consultas(lab):
    identificador = registrar(lab)
    baja = Baja(MotivoBaja.TRASLADO, lab.profesional, datetime.now(UTC), "Otro laboratorio")
    with lab.unidad() as unidad:
        unidad.pacientes.archivar(identificador, baja)
        unidad.commit()
    with lab.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(identificador).archivado is True
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.archivar(identificador, baja)
        with pytest.raises(PacienteArchivado):
            unidad.historial.registrar_consulta(identificador, lab.profesional, NuevaConsulta("X"))
        with pytest.raises(PacienteNoEncontrado):
            unidad.pacientes.archivar(str(ObjectId()), baja)
        with pytest.raises(ProfesionalNoVinculado):
            unidad.pacientes.archivar(identificador, Baja(MotivoBaja.TRASLADO, "x", baja.fecha))
    documento = lab.admin.pacientes.find_one({"_id": ObjectId(identificador)})
    assert documento["estado"] == "Archivado"
    assert documento["motivo_baja"] == "traslado"
    assert documento["detalle_baja"] == "Otro laboratorio"
    assert documento["archivado_por"] == lab.profesional


def test_una_baja_concurrente_se_detecta_al_confirmar(lab):
    """La baja otra solicitud llego entre la lectura y el commit: no se sobrescribe."""
    identificador = registrar(lab)
    baja = Baja(MotivoBaja.ADMINISTRATIVO, lab.profesional, datetime.now(UTC))
    with lab.unidad() as unidad:
        unidad.pacientes.archivar(identificador, baja)  # pasa la lectura: seguia activo
        lab.admin.pacientes.update_one(  # otra solicitud lo archiva primero
            {"_id": ObjectId(identificador)},
            {"$set": {"estado": "Archivado", "fecha_baja": datetime.now(UTC), "motivo_baja": "x"}},
        )
        with pytest.raises(PacienteArchivado):
            unidad.commit()
    assert lab.admin.pacientes.find_one({"_id": ObjectId(identificador)})["motivo_baja"] == "x"


def test_consulta_cuando_la_baja_llega_antes_del_commit_se_rechaza(lab):
    identificador = registrar(lab)
    with lab.unidad() as unidad:
        unidad.historial.registrar_consulta(identificador, lab.profesional, NuevaConsulta("X"))
        lab.admin.pacientes.update_one(
            {"_id": ObjectId(identificador)},
            {"$set": {"estado": "Archivado", "fecha_baja": datetime.now(UTC), "motivo_baja": "x"}},
        )
        with pytest.raises(PacienteArchivado):
            unidad.commit()
    assert lab.admin.consultas.count_documents({"id_paciente": ObjectId(identificador)}) == 0


def test_dos_bajas_simultaneas_solo_una_gana(lab):
    identificador = registrar(lab)
    resultados = []
    barrera = threading.Barrier(2)

    def dar_de_baja():
        baja = Baja(MotivoBaja.ADMINISTRATIVO, lab.profesional, datetime.now(UTC))
        try:
            with lab.unidad() as unidad:
                unidad.pacientes.archivar(identificador, baja)
                barrera.wait(timeout=10)  # ambas pasaron la lectura antes de escribir
                unidad.commit()
            resultados.append("ok")
        except PacienteArchivado:
            resultados.append("archivado")

    hilos = [threading.Thread(target=dar_de_baja) for _ in range(2)]
    [h.start() for h in hilos]
    [h.join(timeout=20) for h in hilos]
    assert sorted(resultados) == ["archivado", "ok"]


def test_sincronizacion_es_idempotente_y_refleja_la_desactivacion(lab, config_local, admin_pg):
    dsn = config_local["HISTORIALES_POSTGRES_ADMIN_DSN"]
    filtro = {"id_profesional_central": lab.profesional}
    assert lab.admin.profesionales.count_documents(filtro) == 1
    admin_pg.execute(
        "UPDATE identidad.profesional SET activo = FALSE WHERE id_profesional = %s",
        (lab.profesional,),
    )
    for _ in range(2):
        assert sincronizar_laboratorio(dsn, [lab.profesional], lab.admin.profesionales) == 1
    assert lab.admin.profesionales.count_documents(filtro) == 1
    assert lab.admin.profesionales.find_one(filtro)["activo"] is False


def test_flujo_completo_por_la_api_con_login_real(lab):
    with TestClient(create_app(Settings())) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": lab.correo, "password": lab.password}
        )
        assert login.status_code == 200
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        creado = client.post(
            "/api/v1/pacientes",
            json={
                "nombres": "Luisa",
                "apellidos": lab.marca,
                "contacto": {"telefono": "1234"},
                "alergias": [{"sustancia": "Polen"}],
            },
            headers=h,
        )
        assert creado.status_code == 201
        pid = creado.json()["id_paciente"]
        busqueda = client.get("/api/v1/pacientes", params={"nombre": f"lui {lab.marca}"}, headers=h)
        assert [f["id_paciente"] for f in busqueda.json()] == [pid]
        consulta = client.post(
            f"/api/v1/pacientes/{pid}/consultas",
            json={
                "motivo": "Hemograma",
                "diagnosticos": [{"descripcion": "Control"}],
                "tratamientos": [{"descripcion": "Reposo"}],
                "recetas": [{"medicamento": "Hierro", "dosis": "1 tab", "frecuencia": "c/24h"}],
            },
            headers=h,
        )
        assert consulta.status_code == 201
        historial = client.get(f"/api/v1/pacientes/{pid}/historial", headers=h)
        assert historial.status_code == 200
        assert historial.json()["consultas"][0]["recetas"][0]["medicamento"] == "Hierro"
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
        assert client.get(f"/api/v1/pacientes/{pid}/odontograma", headers=h).status_code == 501
