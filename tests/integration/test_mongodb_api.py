"""Laboratorio Clinico (MongoDB) con datos sinteticos; se borran al terminar.

Usa la misma cuenta limitada que la API (historiales_app) y la cuenta administrativa solo
para preparar y limpiar. Requiere la base inicializada con laboratorio_clinico_mongo.js.
"""

import threading
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import psycopg
import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from pymongo import MongoClient
from pymongo.errors import WriteError

from app.core.config import Settings
from app.domain.cita import EstadoCita, NuevaCita
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
from app.domain.laboratorio import EstadoOrden, NuevaMuestra, ValorResultado, construir_resultados
from app.domain.paciente import (
    Alergia,
    Baja,
    CambiosPaciente,
    Contacto,
    MotivoBaja,
    NuevoPaciente,
)
from app.infrastructure.persistence.mongodb.unidad import UnidadTrabajoMongo
from app.main import create_app
from scripts.sincronizar_profesionales import sincronizar_laboratorio

PERMISOS = [
    "pacientes:leer",
    "pacientes:registrar",
    "historiales:leer",
    "consultas:registrar",
    "historiales:archivar",
    "citas:leer",
    "citas:gestionar",
    "laboratorio:resultados",
    "laboratorio:validar",
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
    entorno.base_app = app
    entorno.unidad = lambda: UnidadTrabajoMongo(app)
    yield entorno

    ids = [
        p["_id"] for p in admin.pacientes.find({"apellidos": {"$regex": f"^{marca}"}}, {"_id": 1})
    ]
    admin.consultas.delete_many({"id_paciente": {"$in": ids}})
    admin.citas.delete_many({"id_paciente": {"$in": ids}})
    admin.ordenes_laboratorio.delete_many({"id_paciente": {"$in": ids}})
    admin.catalogo_pruebas.delete_many({"codigo": {"$regex": f"^{marca}"}})
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


# ---------------------------------------------------------------------------------------
# Adendas, correccion de datos y citas
# ---------------------------------------------------------------------------------------


def consulta_base(lab, identificador) -> str:
    with lab.unidad() as unidad:
        creada = unidad.historial.registrar_consulta(
            identificador,
            lab.profesional,
            NuevaConsulta("Hemograma", notas="Primera", diagnosticos=(Diagnostico("Anemia"),)),
        )
        unidad.commit()
    return creada.id_consulta


def test_adenda_agrega_sin_reemplazar_y_deja_rastro(lab):
    identificador = registrar(lab)
    id_consulta = consulta_base(lab, identificador)
    adenda = Adenda(
        nota="Resultado confirmado con $literal y {llaves}",
        diagnosticos=(Diagnostico("$Hierro bajo", "D50", "CIE-10"),),
        tratamientos=(Tratamiento("Dieta"),),
        recetas=(Receta("Hierro", "1 tab", "c/24h", duracion_dias=30),),
    )
    with lab.unidad() as unidad:
        devuelta = unidad.historial.agregar_a_consulta(
            identificador, id_consulta, lab.profesional, adenda
        )
        unidad.commit()
    with lab.unidad() as unidad:
        leida = unidad.historial.obtener_consulta(identificador, id_consulta)
    assert leida.notas.startswith("Primera\n\n[Adenda ") and "$literal" in leida.notas
    assert [d.descripcion for d in leida.diagnosticos] == ["Anemia", "$Hierro bajo"]
    assert leida.recetas[0].duracion_dias == 30 and leida.tratamientos[0].descripcion == "Dieta"
    assert (devuelta.notas, devuelta.diagnosticos, devuelta.recetas) == (
        leida.notas,
        leida.diagnosticos,
        leida.recetas,
    )


def test_adenda_sin_commit_o_en_consulta_ajena_no_hace_nada(lab):
    identificador, otro = registrar(lab), registrar(lab, "Otro")
    id_consulta = consulta_base(lab, identificador)
    with lab.unidad() as unidad:
        unidad.historial.agregar_a_consulta(
            identificador, id_consulta, lab.profesional, Adenda(nota="no se confirma")
        )
    with lab.unidad() as unidad:
        assert unidad.historial.obtener_consulta(identificador, id_consulta).notas == "Primera"
        assert unidad.historial.obtener_consulta(otro, id_consulta) is None
        for malo in (id_consulta, "abc", str(ObjectId())):
            with pytest.raises(ConsultaNoEncontrada):
                unidad.historial.agregar_a_consulta(otro, malo, lab.profesional, Adenda(nota="x"))
        with pytest.raises(ProfesionalNoVinculado):
            unidad.historial.agregar_a_consulta(
                identificador, id_consulta, str(uuid4()), Adenda(nota="x")
            )


def test_adendas_simultaneas_no_se_pierden(lab):
    identificador = registrar(lab)
    id_consulta = consulta_base(lab, identificador)
    barrera = threading.Barrier(5)

    def agregar(n):
        with lab.unidad() as unidad:
            unidad.historial.agregar_a_consulta(
                identificador,
                id_consulta,
                lab.profesional,
                Adenda(diagnosticos=(Diagnostico(f"Dx {n}"),)),
            )
            barrera.wait(timeout=10)
            unidad.commit()

    hilos = [threading.Thread(target=agregar, args=(n,)) for n in range(5)]
    [h.start() for h in hilos]
    [h.join(timeout=30) for h in hilos]
    with lab.unidad() as unidad:
        leida = unidad.historial.obtener_consulta(identificador, id_consulta)
    assert len(leida.diagnosticos) == 6 and leida.notas.count("[Adenda ") == 5


def test_adenda_en_historial_archivado_se_rechaza(lab):
    identificador = registrar(lab)
    id_consulta = consulta_base(lab, identificador)
    with lab.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.ADMINISTRATIVO, lab.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with lab.unidad() as unidad, pytest.raises(PacienteArchivado):
        unidad.historial.agregar_a_consulta(
            identificador, id_consulta, lab.profesional, Adenda(nota="x")
        )


def test_corregir_datos_y_agregar_alergias(lab):
    identificador = registrar(lab, contacto=Contacto(telefono="111"), alergias=(Alergia("Latex"),))
    with lab.unidad() as unidad:
        unidad.pacientes.actualizar(
            identificador,
            CambiosPaciente(
                nombres="Ana Maria",
                fecha_nacimiento=date(1991, 2, 3),
                contacto=Contacto(correo="nuevo@example.invalid"),
            ),
        )
        unidad.pacientes.agregar_alergias(identificador, (Alergia("Polen", "Tos"),))
        unidad.commit()
    with lab.unidad() as unidad:
        p = unidad.pacientes.obtener_por_id(identificador)
        assert (p.nombres, p.fecha_nacimiento) == ("Ana Maria", date(1991, 2, 3))
        assert p.contacto == Contacto(None, "nuevo@example.invalid", None)
        assert p.alergias == (Alergia("Latex"), Alergia("Polen", "Tos"))
        with pytest.raises(DatosInvalidos):
            unidad.pacientes.agregar_alergias(identificador, (Alergia("LATEX"),))
        with pytest.raises(DatosInvalidos):
            unidad.pacientes.actualizar(
                identificador, CambiosPaciente(fecha_nacimiento=date.today() + timedelta(days=1))
            )
        with pytest.raises(PacienteNoEncontrado):
            unidad.pacientes.actualizar(str(ObjectId()), CambiosPaciente(nombres="X"))
    # Vaciar el contacto lo quita (el validador no admite textos vacios).
    with lab.unidad() as unidad:
        unidad.pacientes.actualizar(identificador, CambiosPaciente(contacto=Contacto()))
        unidad.commit()
    with lab.unidad() as unidad:
        assert unidad.pacientes.obtener_por_id(identificador).contacto is None


def test_no_se_corrigen_datos_de_historial_archivado(lab):
    identificador = registrar(lab)
    with lab.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.TRASLADO, lab.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with lab.unidad() as unidad:
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.actualizar(identificador, CambiosPaciente(nombres="Nuevo"))
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.agregar_alergias(identificador, (Alergia("Polen"),))


def manana(horas=9) -> datetime:
    base = datetime.now(UTC) + timedelta(days=3)
    return base.replace(hour=horas, minute=0, second=0, microsecond=0)


def nueva_cita(lab, paciente, inicio, minutos=30) -> NuevaCita:
    return NuevaCita(paciente, lab.profesional, inicio, minutos, "Toma de muestra")


def test_perfil_local_del_profesional(lab):
    with lab.unidad() as unidad:
        perfil = unidad.profesionales.obtener(lab.profesional)
        assert unidad.profesionales.obtener(str(uuid4())) is None
        assert unidad.profesionales.obtener("no-es-uuid") is None
    assert perfil.id_profesional == lab.profesional and perfil.activo and perfil.atiende_pacientes


def test_cita_ida_y_vuelta_y_listados(lab):
    identificador = registrar(lab)
    inicio = manana(15)
    with lab.unidad() as unidad:
        cita = unidad.citas.agendar(
            nueva_cita(lab, identificador, inicio, 45), "Ana", lab.profesional
        )
        unidad.commit()
    assert cita.estado == EstadoCita.PROGRAMADA and cita.fin == inicio + timedelta(minutes=45)
    with lab.unidad() as unidad:
        assert unidad.citas.obtener(cita.id_cita) == cita
        assert unidad.citas.listar_agenda(
            inicio - timedelta(hours=1), inicio + timedelta(hours=1), lab.profesional
        ) == [cita]
        assert (
            unidad.citas.listar_agenda(inicio + timedelta(hours=1), inicio + timedelta(hours=2))
            == []
        )
        assert unidad.citas.listar_agenda(inicio, inicio + timedelta(hours=1), "xx") == []
        assert unidad.citas.listar_por_paciente(identificador, 5) == [cita]
        assert unidad.citas.obtener("abc") is None


def test_choques_cancelacion_y_transiciones(lab):
    a, b = registrar(lab), registrar(lab, "Beto")
    inicio = manana()
    with lab.unidad() as unidad:
        primera = unidad.citas.agendar(nueva_cita(lab, a, inicio), "A", lab.profesional)
        unidad.commit()
    with lab.unidad() as unidad:
        unidad.citas.agendar(
            nueva_cita(lab, b, inicio + timedelta(minutes=10)), "B", lab.profesional
        )
        with pytest.raises(ConflictoAgenda):
            unidad.commit()
    with lab.unidad() as unidad:  # justo al terminar la primera no se cruza
        unidad.citas.agendar(
            nueva_cita(lab, b, inicio + timedelta(minutes=30)), "B", lab.profesional
        )
        unidad.commit()
    with lab.unidad() as unidad:
        unidad.citas.cambiar_estado(primera.id_cita, EstadoCita.CONFIRMADA, lab.profesional, None)
        unidad.commit()
    with lab.unidad() as unidad:  # confirmada sigue ocupando el horario
        unidad.citas.agendar(nueva_cita(lab, b, inicio), "B", lab.profesional)
        with pytest.raises(ConflictoAgenda):
            unidad.commit()
    with lab.unidad() as unidad:
        cancelada = unidad.citas.cambiar_estado(
            primera.id_cita, EstadoCita.CANCELADA, lab.profesional, "Paciente avisa"
        )
        unidad.commit()
    assert cancelada.estado == EstadoCita.CANCELADA and cancelada.motivo_cambio == "Paciente avisa"
    with lab.unidad() as unidad:  # cancelar libera el horario
        unidad.citas.agendar(nueva_cita(lab, b, inicio), "B", lab.profesional)
        unidad.commit()
    with lab.unidad() as unidad:
        with pytest.raises(ConflictoAgenda):  # estado final
            unidad.citas.cambiar_estado(
                primera.id_cita, EstadoCita.CONFIRMADA, lab.profesional, None
            )
        with pytest.raises(CitaNoEncontrada):
            unidad.citas.cambiar_estado(str(ObjectId()), EstadoCita.CANCELADA, lab.profesional, "x")


def test_cita_a_archivado_o_a_profesional_inexistente(lab):
    identificador = registrar(lab)
    with lab.unidad() as unidad:
        with pytest.raises(DatosInvalidos):
            unidad.citas.agendar(
                NuevaCita(identificador, str(uuid4()), manana(), 30, "x"), "A", lab.profesional
            )
        with pytest.raises(PacienteNoEncontrado):
            unidad.citas.agendar(nueva_cita(lab, str(ObjectId()), manana()), "A", lab.profesional)
    with lab.unidad() as unidad:
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.TRASLADO, lab.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with lab.unidad() as unidad, pytest.raises(PacienteArchivado):
        unidad.citas.agendar(nueva_cita(lab, identificador, manana()), "A", lab.profesional)


def test_dos_reservas_simultaneas_del_mismo_horario_solo_una_gana(lab):
    a, b = registrar(lab), registrar(lab, "Beto")
    inicio = manana(18)
    resultados = []
    barrera = threading.Barrier(2)

    def reservar(paciente):
        try:
            with lab.unidad() as unidad:
                unidad.citas.agendar(nueva_cita(lab, paciente, inicio), "X", lab.profesional)
                barrera.wait(timeout=10)
                unidad.commit()
            resultados.append("ok")
        except ConflictoAgenda:
            resultados.append("choque")

    hilos = [threading.Thread(target=reservar, args=(p,)) for p in (a, b)]
    [h.start() for h in hilos]
    [h.join(timeout=30) for h in hilos]
    assert sorted(resultados) == ["choque", "ok"]


def test_adenda_correccion_y_citas_por_la_api(lab):
    with TestClient(create_app(Settings())) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": lab.correo, "password": lab.password}
        )
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        pid = client.post(
            "/api/v1/pacientes", json={"nombres": "Rosa", "apellidos": lab.marca}, headers=h
        ).json()["id_paciente"]
        consulta = client.post(
            f"/api/v1/pacientes/{pid}/consultas", json={"motivo": "Perfil"}, headers=h
        ).json()
        ruta = f"/api/v1/pacientes/{pid}/consultas/{consulta['id_consulta']}"
        assert client.post(ruta + "/adenda", json={}, headers=h).status_code == 422
        agregada = client.post(
            ruta + "/adenda", json={"diagnosticos": [{"descripcion": "Normal"}]}, headers=h
        )
        assert agregada.status_code == 200 and client.get(ruta, headers=h).json() == agregada.json()
        assert (
            client.patch(
                f"/api/v1/pacientes/{pid}", json={"nombres": "Rosa Maria"}, headers=h
            ).json()["nombres"]
            == "Rosa Maria"
        )
        assert (
            client.post(
                f"/api/v1/pacientes/{pid}/alergias",
                json={"alergias": [{"sustancia": "Latex"}]},
                headers=h,
            ).status_code
            == 200
        )
        cuerpo = {
            "id_paciente": pid,
            "id_profesional": lab.profesional,
            "inicio": manana(16).isoformat(),
            "duracion_minutos": 30,
            "motivo": "Toma",
        }
        cita = client.post("/api/v1/citas", json=cuerpo, headers=h)
        assert cita.status_code == 201, cita.text
        assert client.post("/api/v1/citas", json=cuerpo, headers=h).status_code == 409
        cancelada = client.post(
            f"/api/v1/citas/{cita.json()['id_cita']}/estado",
            json={"estado": "cancelada", "motivo": "Reprogramar"},
            headers=h,
        )
        assert cancelada.status_code == 200 and cancelada.json()["estado"] == "cancelada"


# ---------------------------------------------------------------------------------------
# Laboratorio: catalogo, ordenes, resultados y validacion
# ---------------------------------------------------------------------------------------


def cargar_prueba(lab, sufijo="HGB", version=1, activo=True, maximo=17.0) -> str:
    """El catalogo lo carga la cuenta administrativa (scripts/cargar_catalogo_laboratorio)."""
    codigo = f"{lab.marca}-{sufijo}"
    lab.admin.catalogo_pruebas.insert_one(
        {
            "codigo": codigo,
            "nombre": f"Prueba {sufijo}",
            "version": version,
            "activo": activo,
            "tipo_muestra": "sangre",
            "parametros": [
                {
                    "codigo": "HGB",
                    "nombre": "Hemoglobina",
                    "unidad": "g/dL",
                    "tipo_valor": "numerico",
                    "referencia": {"minimo": 12.0, "maximo": maximo, "poblacion": "adultos"},
                },
                {"codigo": "NOTA", "nombre": "Aspecto", "tipo_valor": "texto"},
                {"codigo": "HEMOL", "nombre": "Hemolizada", "tipo_valor": "booleano"},
            ],
        }
    )
    return codigo


def orden_base(lab, identificador, codigos) -> tuple[str, object]:
    id_consulta = consulta_base(lab, identificador)
    with lab.unidad() as unidad:
        orden = unidad.laboratorio.solicitar(identificador, id_consulta, lab.profesional, codigos)
        unidad.commit()
    return id_consulta, orden


def valores_hgb(valor):
    return (ValorResultado("HGB", valor),)


def registrar_hgb(lab, identificador, orden, codigo, valor):
    prueba = next(p for p in orden.pruebas if p.codigo == codigo)
    resultados = construir_resultados(prueba, valores_hgb(valor))
    with lab.unidad() as unidad:
        devuelta = unidad.laboratorio.registrar_resultados(
            identificador,
            orden.id_orden,
            codigo,
            resultados,
            None,
            lab.profesional,
            datetime.now(UTC),
        )
        unidad.commit()
    return devuelta


def test_catalogo_muestra_solo_la_version_activa_mas_reciente(lab):
    activa = cargar_prueba(lab, "A", version=1)
    lab.admin.catalogo_pruebas.update_one({"codigo": activa}, {"$set": {"nombre": "Vieja"}})
    cargar_prueba(lab, "B", version=1)
    lab.admin.catalogo_pruebas.insert_one(
        {
            **lab.admin.catalogo_pruebas.find_one({"codigo": activa}, {"_id": 0}),
            "version": 2,
            "nombre": "Nueva",
        }
    )
    cargar_prueba(lab, "C", activo=False)
    with lab.unidad() as unidad:
        propias = {
            p.codigo: p
            for p in unidad.laboratorio.listar_catalogo()
            if p.codigo.startswith(lab.marca)
        }
    assert set(propias) == {activa, f"{lab.marca}-B"}
    assert (propias[activa].version, propias[activa].nombre) == (2, "Nueva")
    assert propias[activa].parametros[0].referencia.maximo == 17.0


def test_la_orden_guarda_copia_de_la_prueba_y_no_cambia_con_el_catalogo(lab):
    identificador = registrar(lab)
    codigo = cargar_prueba(lab)
    id_consulta, orden = orden_base(lab, identificador, (codigo,))
    assert orden.estado == EstadoOrden.SOLICITADA and orden.numero_orden.startswith("ORD-")
    lab.admin.catalogo_pruebas.update_one(
        {"codigo": codigo}, {"$set": {"parametros.0.referencia.maximo": 99.0, "nombre": "Otra"}}
    )
    with lab.unidad() as unidad:
        leida = unidad.laboratorio.obtener(identificador, orden.id_orden)
        assert unidad.laboratorio.listar(identificador, 5) == [leida]
        assert unidad.laboratorio.obtener(registrar(lab, "Otro"), orden.id_orden) is None
        assert unidad.laboratorio.obtener("abc", orden.id_orden) is None
    assert leida.id_consulta == id_consulta and leida.numero_orden == orden.numero_orden
    assert leida.pruebas[0].nombre == "Prueba HGB"  # no "Otra"
    assert leida.pruebas[0].parametros[0].referencia.maximo == 17.0


def test_solicitar_exige_catalogo_commit_y_paciente_activo(lab):
    identificador = registrar(lab)
    codigo = cargar_prueba(lab)
    id_consulta = consulta_base(lab, identificador)
    with lab.unidad() as unidad, pytest.raises(DatosInvalidos):
        unidad.laboratorio.solicitar(identificador, id_consulta, lab.profesional, ("NOEXISTE",))
    with lab.unidad() as unidad:  # sin commit no se guarda
        unidad.laboratorio.solicitar(identificador, id_consulta, lab.profesional, (codigo,))
    with lab.unidad() as unidad:
        assert unidad.laboratorio.listar(identificador, 5) == []
        unidad.pacientes.archivar(
            identificador, Baja(MotivoBaja.TRASLADO, lab.profesional, datetime.now(UTC))
        )
        unidad.commit()
    with lab.unidad() as unidad:
        unidad.laboratorio.solicitar(identificador, id_consulta, lab.profesional, (codigo,))
        with pytest.raises(PacienteArchivado):
            unidad.commit()


def test_resultados_se_interpretan_con_el_rango_de_la_orden(lab):
    identificador = registrar(lab)
    codigo = cargar_prueba(lab)
    _, orden = orden_base(lab, identificador, (codigo,))
    prueba = orden.pruebas[0]
    for valor, esperado in ((9.5, "bajo"), (14, "normal"), (17.5, "alto"), (12, "normal")):
        assert construir_resultados(prueba, valores_hgb(valor))[0].interpretacion == esperado
    mixto = construir_resultados(
        prueba,
        (
            ValorResultado("NOTA", "Claro"),
            ValorResultado("HEMOL", False),
            ValorResultado("HGB", 13),
        ),
    )
    assert [r.interpretacion for r in mixto] == [None, None, "normal"]
    for malo in (
        (ValorResultado("XXX", 1),),
        (ValorResultado("HGB", "alto"),),
        (ValorResultado("HGB", True),),
        (ValorResultado("HEMOL", 1),),
        (ValorResultado("NOTA", "  "),),
        (ValorResultado("HGB", 1), ValorResultado("HGB", 2)),
    ):
        with pytest.raises(DatosInvalidos):
            construir_resultados(prueba, malo)


def test_muestras_resultados_y_validacion_con_trazabilidad(lab):
    identificador = registrar(lab)
    codigo = cargar_prueba(lab)
    _, orden = orden_base(lab, identificador, (codigo,))
    with lab.unidad() as unidad:
        unidad.laboratorio.registrar_muestra(
            identificador,
            orden.id_orden,
            NuevaMuestra("sangre", condicion="Ayuno"),
            datetime.now(UTC),
        )
        unidad.commit()
    en_proceso = registrar_hgb(lab, identificador, orden, codigo, 10.0)
    assert en_proceso.estado == EstadoOrden.EN_PROCESO
    corregido = registrar_hgb(lab, identificador, orden, codigo, 14.0)  # corregir antes de validar
    with lab.unidad() as unidad:
        validada = unidad.laboratorio.validar(
            identificador, orden.id_orden, lab.profesional, datetime.now(UTC)
        )
        unidad.commit()
    with lab.unidad() as unidad:
        leida = unidad.laboratorio.obtener(identificador, orden.id_orden)
    assert corregido.pruebas[0].resultados[0].valor == 14.0
    assert leida.estado == EstadoOrden.VALIDADA and leida.validada_por == lab.profesional
    assert leida.muestras[0].codigo == "M1" and leida.muestras[0].condicion == "Ayuno"
    assert leida.pruebas[0].resultados[0].valor == 14.0 and len(leida.pruebas[0].resultados) == 1
    assert leida.pruebas[0].registrado_por == lab.profesional
    assert validada.validada_en is not None


def test_orden_validada_o_cancelada_ya_no_cambia(lab):
    identificador = registrar(lab)
    codigo = cargar_prueba(lab)
    _, validada = orden_base(lab, identificador, (codigo,))
    _, cancelada = orden_base(lab, identificador, (codigo,))
    registrar_hgb(lab, identificador, validada, codigo, 14)
    ahora = datetime.now(UTC)
    with lab.unidad() as unidad:
        unidad.laboratorio.validar(identificador, validada.id_orden, lab.profesional, ahora)
        unidad.laboratorio.cancelar(
            identificador, cancelada.id_orden, "Pedida por error", lab.profesional, ahora
        )
        unidad.commit()
    for orden in (validada, cancelada):
        with lab.unidad() as unidad:
            for operacion in (
                lambda u: u.laboratorio.registrar_muestra(
                    identificador, orden.id_orden, NuevaMuestra("orina"), ahora
                ),
                lambda u: u.laboratorio.validar(
                    identificador, orden.id_orden, lab.profesional, ahora
                ),
                lambda u: u.laboratorio.cancelar(
                    identificador, orden.id_orden, "x", lab.profesional, ahora
                ),
            ):
                operacion(unidad)
                with pytest.raises(ConflictoEstado):
                    unidad.commit()
    with lab.unidad() as unidad:
        assert unidad.laboratorio.obtener(identificador, cancelada.id_orden).motivo_cancelacion == (
            "Pedida por error"
        )
        with pytest.raises(RegistroNoEncontrado):
            unidad.laboratorio.registrar_muestra(
                identificador, str(ObjectId()), NuevaMuestra("orina"), ahora
            )


def test_la_base_rechaza_validar_sin_resultados_aunque_se_salten_la_api(lab):
    identificador = registrar(lab)
    codigo = cargar_prueba(lab)
    _, orden = orden_base(lab, identificador, (codigo,))
    ahora = datetime.now(UTC)
    with pytest.raises(WriteError):
        lab.base_app.ordenes_laboratorio.update_one(
            {"_id": ObjectId(orden.id_orden)},
            {"$set": {"estado": "Validada", "validada_en": ahora, "validada_por": lab.profesional}},
        )
    with pytest.raises(WriteError):  # cancelar exige motivo
        lab.base_app.ordenes_laboratorio.update_one(
            {"_id": ObjectId(orden.id_orden)}, {"$set": {"estado": "Cancelada"}}
        )


def test_dos_validaciones_simultaneas_solo_una_gana(lab):
    identificador = registrar(lab)
    codigo = cargar_prueba(lab)
    _, orden = orden_base(lab, identificador, (codigo,))
    registrar_hgb(lab, identificador, orden, codigo, 14)
    resultados = []
    barrera = threading.Barrier(2)

    def validar():
        try:
            with lab.unidad() as unidad:
                unidad.laboratorio.validar(
                    identificador, orden.id_orden, lab.profesional, datetime.now(UTC)
                )
                barrera.wait(timeout=10)
                unidad.commit()
            resultados.append("ok")
        except ConflictoEstado:
            resultados.append("conflicto")

    hilos = [threading.Thread(target=validar) for _ in range(2)]
    [h.start() for h in hilos]
    [h.join(timeout=30) for h in hilos]
    assert sorted(resultados) == ["conflicto", "ok"]


def test_flujo_de_laboratorio_por_la_api(lab):
    codigo = cargar_prueba(lab)
    with TestClient(create_app(Settings())) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": lab.correo, "password": lab.password}
        )
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        catalogo = client.get("/api/v1/laboratorio/pruebas", headers=h)
        assert codigo in [p["codigo"] for p in catalogo.json()]
        pid = client.post(
            "/api/v1/pacientes", json={"nombres": "Rosa", "apellidos": lab.marca}, headers=h
        ).json()["id_paciente"]
        consulta = client.post(
            f"/api/v1/pacientes/{pid}/consultas", json={"motivo": "Chequeo"}, headers=h
        ).json()
        base = f"/api/v1/pacientes/{pid}/ordenes"
        for malo in (
            {"id_consulta": consulta["id_consulta"], "pruebas": []},
            {"id_consulta": consulta["id_consulta"], "pruebas": ["NOEXISTE"]},
            {"id_consulta": consulta["id_consulta"], "pruebas": [codigo, codigo]},
        ):
            assert client.post(base, json=malo, headers=h).status_code == 422
        assert (
            client.post(
                base,
                json={"id_consulta": "999999999999999999999999", "pruebas": [codigo]},
                headers=h,
            ).status_code
            == 404
        )
        creada = client.post(
            base, json={"id_consulta": consulta["id_consulta"], "pruebas": [codigo]}, headers=h
        )
        assert creada.status_code == 201, creada.text
        oid = creada.json()["id_orden"]
        ruta = f"{base}/{oid}"
        assert client.post(ruta + "/validar", headers=h).status_code == 422  # sin resultados
        muestra = client.post(ruta + "/muestras", json={"tipo": "sangre"}, headers=h)
        assert muestra.status_code == 200 and muestra.json()["muestras"][0]["codigo"] == "M1"
        res = f"{ruta}/pruebas/{codigo}/resultados"
        assert (
            client.put(
                res, json={"valores": [{"codigo_parametro": "HGB", "valor": "x"}]}, headers=h
            ).status_code
            == 422
        )
        assert (
            client.put(
                res, json={"valores": [{"codigo_parametro": "XX", "valor": 1}]}, headers=h
            ).status_code
            == 422
        )
        assert (
            client.put(
                f"{ruta}/pruebas/NOEXISTE/resultados",
                json={"valores": [{"codigo_parametro": "HGB", "valor": 1}]},
                headers=h,
            ).status_code
            == 404
        )
        puesto = client.put(
            res,
            json={
                "valores": [
                    {"codigo_parametro": "HGB", "valor": 9.1},
                    {"codigo_parametro": "HEMOL", "valor": False},
                ],
                "observaciones": "Repetir en ayunas",
            },
            headers=h,
        )
        assert puesto.status_code == 200, puesto.text
        assert puesto.json()["estado"] == "en_proceso"
        hgb = puesto.json()["pruebas"][0]["resultados"][0]
        assert (hgb["valor"], hgb["interpretacion"], hgb["unidad"]) == (9.1, "bajo", "g/dL")
        assert client.get(ruta, headers=h).json() == puesto.json()
        assert [o["id_orden"] for o in client.get(base, headers=h).json()] == [oid]
        validada = client.post(ruta + "/validar", headers=h)
        assert validada.status_code == 200 and validada.json()["estado"] == "validada"
        assert (
            client.put(
                res, json={"valores": [{"codigo_parametro": "HGB", "valor": 14}]}, headers=h
            ).status_code
            == 409
        )
        assert client.post(ruta + "/cancelar", json={"motivo": "x"}, headers=h).status_code == 409
        assert client.post(ruta + "/muestras", json={"tipo": "orina"}, headers=h).status_code == 409
        assert client.get(f"{base}/{ObjectId()}", headers=h).status_code == 404


def test_script_de_carga_de_pruebas_publica_versiones_inmutables(lab):
    from scripts.cargar_catalogos import CatalogoInvalido, cargar_pruebas

    codigo = f"{lab.marca}-GLU"

    def prueba(version=1, maximo=99):
        return {
            "codigo": codigo,
            "nombre": "Glucosa",
            "version": version,
            "parametros": [
                {
                    "codigo": "GLU",
                    "nombre": "Glucosa",
                    "tipo_valor": "numerico",
                    "unidad": "mg/dL",
                    "referencia": {"minimo": 70, "maximo": maximo},
                }
            ],
        }

    catalogo = lab.admin.catalogo_pruebas
    assert cargar_pruebas(catalogo, {"pruebas": [prueba()]}) == {
        "publicadas": 1,
        "sin_cambios": 0,
        "desactivadas": 0,
    }
    assert cargar_pruebas(catalogo, {"pruebas": [prueba()]})["sin_cambios"] == 1
    with pytest.raises(CatalogoInvalido):  # cambiar un rango exige una version nueva
        cargar_pruebas(catalogo, {"pruebas": [prueba(maximo=110)]})
    nueva = cargar_pruebas(
        catalogo, {"pruebas": [prueba(version=2, maximo=110)]}, desactivar_anteriores=True
    )
    assert nueva == {"publicadas": 1, "sin_cambios": 0, "desactivadas": 1}
    assert catalogo.find_one({"codigo": codigo, "version": 1})["activo"] is False
    for malo in (
        {},
        {"pruebas": [{"codigo": codigo, "nombre": "x", "parametros": []}]},
        {
            "pruebas": [
                {**prueba(), "parametros": [{"codigo": "A", "nombre": "A", "tipo_valor": "x"}]}
            ]
        },
    ):
        with pytest.raises(CatalogoInvalido):
            cargar_pruebas(catalogo, malo)
    with lab.unidad() as unidad:
        activas = [p for p in unidad.laboratorio.listar_catalogo() if p.codigo == codigo]
    assert [p.version for p in activas] == [2]


# ---------------------------------------------------------------------------------------
# Tablero de ordenes de la institucion y versiones del catalogo
# ---------------------------------------------------------------------------------------


def test_tablero_de_ordenes_de_toda_la_institucion(lab):
    primero, segundo = registrar(lab, "Uno"), registrar(lab, "Dos")
    codigo, otra = cargar_prueba(lab, "T1"), cargar_prueba(lab, "T2")
    _, orden_1 = orden_base(lab, primero, (codigo, otra))
    _, orden_2 = orden_base(lab, segundo, (codigo,))
    with lab.unidad() as unidad:
        unidad.laboratorio.registrar_muestra(
            primero, orden_1.id_orden, NuevaMuestra("sangre"), datetime.now(UTC)
        )
        unidad.commit()
    registrar_hgb(lab, primero, orden_1, codigo, 13.5)
    propias = {orden_1.id_orden, orden_2.id_orden}
    with lab.unidad() as unidad:
        todas = [
            o for o in unidad.laboratorio.listar_institucion(None, 200) if o.id_orden in propias
        ]
        solicitadas = unidad.laboratorio.listar_institucion(
            frozenset({EstadoOrden.SOLICITADA}), 200
        )
        primera_pagina = unidad.laboratorio.listar_institucion(None, 1)
        siguiente = unidad.laboratorio.listar_institucion(
            None, 200, primera_pagina[0].solicitada_en
        )
    assert [o.id_orden for o in todas] == [orden_2.id_orden, orden_1.id_orden]  # recientes
    fila_1 = todas[1]
    assert fila_1.nombre_paciente == f"Uno {lab.marca}"
    assert fila_1.estado == EstadoOrden.EN_PROCESO and fila_1.muestras == 1
    assert [(p.codigo, p.con_resultados) for p in fila_1.pruebas] == [(codigo, True), (otra, False)]
    assert fila_1.pruebas_pendientes == 1
    assert orden_2.id_orden in {o.id_orden for o in solicitadas}
    assert orden_1.id_orden not in {o.id_orden for o in solicitadas}
    assert all(o.solicitada_en < primera_pagina[0].solicitada_en for o in siguiente)

    with TestClient(create_app(Settings())) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": lab.correo, "password": lab.password}
        )
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        respuesta = client.get(
            "/api/v1/laboratorio/ordenes",
            params=[("estado", "solicitada"), ("estado", "en_proceso"), ("limite", 200)],
            headers=h,
        )
        malo = client.get("/api/v1/laboratorio/ordenes", params={"estado": "x"}, headers=h)
    assert respuesta.status_code == 200 and malo.status_code == 422
    fila = next(f for f in respuesta.json() if f["id_orden"] == orden_1.id_orden)
    assert fila["pruebas_pendientes"] == 1 and fila["nombre_paciente"] == f"Uno {lab.marca}"
    # Sin valores clinicos en el tablero.
    assert all("resultados" not in p for p in fila["pruebas"]) and "13.5" not in str(fila)


def test_versiones_de_una_prueba_del_catalogo(lab):
    codigo = cargar_prueba(lab, "VER", version=1, maximo=16.0)
    cargar_prueba(lab, "VER", version=2, maximo=17.0)
    cargar_prueba(lab, "VER", version=3, activo=False, maximo=18.0)
    with lab.unidad() as unidad:
        versiones = unidad.laboratorio.versiones(codigo)
        assert unidad.laboratorio.versiones(f"{lab.marca}-NOEXISTE") == []
        assert unidad.laboratorio.versiones({"$ne": None}) == []  # sin inyeccion de operadores
    assert [(v.prueba.version, v.activa, v.vigente) for v in versiones] == [
        (3, False, False),
        (2, True, True),
        (1, True, False),
    ]
    assert versiones[2].prueba.parametros[0].referencia.maximo == 16.0
    with TestClient(create_app(Settings())) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": lab.correo, "password": lab.password}
        )
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        api = client.get(f"/api/v1/laboratorio/pruebas/{codigo}/versiones", headers=h)
        ausente = client.get("/api/v1/laboratorio/pruebas/NOEXISTE-X/versiones", headers=h)
    assert [v["prueba"]["version"] for v in api.json()] == [3, 2, 1]
    assert api.json()[1]["vigente"] is True and ausente.status_code == 404


def test_tablero_no_omite_ordenes_con_la_misma_fecha_y_resumen_global(lab):
    identificador = registrar(lab)
    codigo = cargar_prueba(lab, "CURSOR")
    _, primera = orden_base(lab, identificador, (codigo,))
    _, segunda = orden_base(lab, identificador, (codigo,))
    instante = datetime.now(UTC).replace(microsecond=0)
    lab.admin.ordenes_laboratorio.update_many(
        {"_id": {"$in": [ObjectId(primera.id_orden), ObjectId(segunda.id_orden)]}},
        {"$set": {"solicitada_en": instante}},
    )
    with lab.unidad() as unidad:
        una = unidad.laboratorio.listar_institucion(None, 1)[0]
        resto = unidad.laboratorio.listar_institucion(None, 200, una.solicitada_en, una.id_orden)
        conteos = unidad.laboratorio.resumen()
    assert {primera.id_orden, segunda.id_orden} <= {una.id_orden, *(o.id_orden for o in resto)}
    assert conteos["solicitada"] >= 2
    with TestClient(create_app(Settings())) as client:
        login = client.post(
            "/api/v1/auth/login", json={"correo": lab.correo, "password": lab.password}
        )
        h = {"Authorization": "Bearer " + login.json()["access_token"]}
        siguiente = client.get(
            "/api/v1/laboratorio/ordenes",
            params={
                "antes_de": una.solicitada_en.isoformat(),
                "antes_de_id": una.id_orden,
            },
            headers=h,
        )
        assert siguiente.status_code == 200
        resumen = client.get("/api/v1/laboratorio/resumen", headers=h)
        assert resumen.status_code == 200 and resumen.json() == conteos
        assert (
            client.get(
                "/api/v1/laboratorio/ordenes", params={"antes_de_id": una.id_orden}, headers=h
            ).status_code
            == 422
        )
