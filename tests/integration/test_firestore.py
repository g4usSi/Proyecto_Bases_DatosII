"""Prueba real contra el proyecto Firebase configurado en .env.

Se ejecuta solo con HISTORIALES_TEST_INTEGRATION=1 y si existe la clave. Crea un
paciente sintetico y lo borra al terminar.
"""

import os
import threading
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.config import Settings
from app.domain.odontograma import EstadoDental
from app.domain.paciente import NuevoPaciente


@pytest.fixture
def cliente_firestore():
    emulador = os.environ.get("FIRESTORE_EMULATOR_HOST")
    if emulador:
        # Emulador local de Firestore (sin proyecto real ni clave): datos desechables.
        from google.auth.credentials import AnonymousCredentials
        from google.cloud import firestore

        cliente = firestore.Client(project="prueba-local", credentials=AnonymousCredentials())
        try:
            yield cliente
        finally:
            cliente.close()
        return
    settings = Settings()
    if settings.firestore_credentials is None or not settings.firestore_credentials.is_file():
        pytest.skip("Sin clave de Firebase configurada.")
    from app.infrastructure.persistence.firestore.cliente import crear_cliente_firestore

    cliente, cerrar = crear_cliente_firestore(
        settings.firestore_credentials,
        settings.firestore_project_id,
        settings.firestore_database,
    )
    try:
        yield cliente
    finally:
        cerrar()


def test_registrar_y_leer_paciente_sintetico(cliente_firestore):
    from app.infrastructure.persistence.firestore.unidad import (
        COLECCION_PACIENTES,
        UnidadTrabajoFirestore,
    )

    datos = NuevoPaciente("Paciente Firestore sintetico", "Prueba", date(2015, 3, 9))
    with UnidadTrabajoFirestore(cliente_firestore) as unidad:
        creado = unidad.pacientes.registrar(datos)
        # Antes de commit no existe: el batch todavia no se envio.
        assert unidad.pacientes.obtener_por_id(creado.id_paciente) is None
        unidad.commit()
    try:
        with UnidadTrabajoFirestore(cliente_firestore) as unidad:
            leido = unidad.pacientes.obtener_por_id(creado.id_paciente)
        assert leido is not None
        assert leido.fecha_nacimiento == date(2015, 3, 9)
        assert leido.archivado is False
    finally:
        cliente_firestore.collection(COLECCION_PACIENTES).document(creado.id_paciente).delete()


def test_rollback_descarta_escrituras(cliente_firestore):
    from app.infrastructure.persistence.firestore.unidad import UnidadTrabajoFirestore

    with UnidadTrabajoFirestore(cliente_firestore) as unidad:
        creado = unidad.pacientes.registrar(NuevoPaciente("Descartado", "Prueba"))
        unidad.rollback()
        unidad.commit()  # el batch nuevo esta vacio: no escribe nada
        assert unidad.pacientes.obtener_por_id(creado.id_paciente) is None


@pytest.mark.parametrize("identificador", ["a/b", ".", "..", "__x__"])
def test_ids_invalidos_no_consultan(cliente_firestore, identificador):
    from app.infrastructure.persistence.firestore.unidad import UnidadTrabajoFirestore

    with UnidadTrabajoFirestore(cliente_firestore) as unidad:
        assert unidad.pacientes.obtener_por_id(identificador) is None


# --- Consultas, archivo, citas y odontograma (datos sinteticos, se borran al final) ---


@pytest.fixture
def unidad_firestore(cliente_firestore):
    from app.infrastructure.persistence.firestore.unidad import UnidadTrabajoFirestore

    return lambda: UnidadTrabajoFirestore(cliente_firestore)


@pytest.fixture
def paciente_sintetico(cliente_firestore, unidad_firestore):
    from app.domain.paciente import Alergia, Contacto

    with unidad_firestore() as unidad:
        paciente = unidad.pacientes.registrar(
            NuevoPaciente(
                "Paciente sintetico",
                "Firestore",
                contacto=Contacto(telefono="0000-0000"),
                alergias=(Alergia("Latex", severidad="leve"),),
            )
        )
        unidad.commit()
    yield paciente.id_paciente
    _borrar_paciente(cliente_firestore, paciente.id_paciente)


def _borrar_paciente(cliente, id_paciente):
    referencia = cliente.collection("pacientes").document(id_paciente)
    for sub in ("consultas", "odontograma"):
        for documento in referencia.collection(sub).stream():
            documento.reference.delete()
    for cita in (
        cliente.collection("citas")
        .where(filter=FieldFilter("id_paciente", "==", id_paciente))
        .stream()
    ):
        cita.reference.delete()
    referencia.delete()


def test_contacto_y_alergias_embebidos(unidad_firestore, paciente_sintetico):
    with unidad_firestore() as unidad:
        paciente = unidad.pacientes.obtener_por_id(paciente_sintetico)
    assert paciente.contacto.telefono == "0000-0000"
    assert paciente.alergias[0].sustancia == "Latex"


def test_consultas_paginadas_y_archivo(unidad_firestore, paciente_sintetico):
    from app.domain.consulta import Diagnostico, NuevaConsulta, Receta
    from app.domain.errores import PacienteArchivado
    from app.domain.paciente import Baja, MotivoBaja

    with unidad_firestore() as unidad:
        for numero in range(3):
            unidad.historial.registrar_consulta(
                paciente_sintetico,
                "00000000-0000-0000-0000-000000000000",
                NuevaConsulta(
                    f"Control {numero}",
                    diagnosticos=(Diagnostico("Caries", "K02", "CIE-10"),),
                    recetas=(Receta("Ibuprofeno", "400 mg", "c/8h"),),
                ),
            )
        primera = unidad.historial.listar_consultas(paciente_sintetico, 2)
        segunda = unidad.historial.listar_consultas(paciente_sintetico, 2, primera[-1].fecha_hora)
    assert [c.motivo for c in primera] == ["Control 2", "Control 1"]
    assert [c.motivo for c in segunda] == ["Control 0"]
    assert primera[0].diagnosticos[0].codigo == "K02"

    baja = Baja(MotivoBaja.TRASLADO, "prof", datetime.now(UTC), "Otra clinica")
    with unidad_firestore() as unidad:
        unidad.pacientes.archivar(paciente_sintetico, baja)
        assert unidad.pacientes.obtener_por_id(paciente_sintetico).archivado
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.archivar(paciente_sintetico, baja)
        with pytest.raises(PacienteArchivado):
            unidad.historial.registrar_consulta(paciente_sintetico, "p", NuevaConsulta("x"))


def test_citas_sin_cruces_y_cancelacion_libera_horario(
    cliente_firestore, unidad_firestore, paciente_sintetico
):
    from app.domain.cita import EstadoCita, NuevaCita
    from app.domain.errores import ConflictoAgenda

    profesional = f"prueba-{uuid4()}"
    inicio = datetime(2030, 1, 15, 23, 30, tzinfo=UTC)  # 17:30 en Guatemala
    try:
        with unidad_firestore() as unidad:
            cita = unidad.citas.agendar(
                NuevaCita(paciente_sintetico, profesional, inicio, 60, "Limpieza"), "P F", "s"
            )
            with pytest.raises(ConflictoAgenda):
                unidad.citas.agendar(
                    NuevaCita(
                        paciente_sintetico, profesional, inicio + timedelta(minutes=30), 30, "x"
                    ),
                    "P F",
                    "s",
                )
            agenda = unidad.citas.listar_agenda(
                inicio - timedelta(hours=1), inicio + timedelta(hours=1), profesional
            )
            assert [c.id_cita for c in agenda] == [cita.id_cita]
            assert unidad.citas.listar_por_paciente(paciente_sintetico, 10)[0].motivo == "Limpieza"
            cancelada = unidad.citas.cambiar_estado(
                cita.id_cita, EstadoCita.CANCELADA, "s", "Reprograma"
            )
            assert cancelada.estado == EstadoCita.CANCELADA
            with pytest.raises(ConflictoAgenda):
                unidad.citas.cambiar_estado(cita.id_cita, EstadoCita.ATENDIDA, "s", None)
            # El horario quedo libre: se puede volver a reservar.
            unidad.citas.agendar(
                NuevaCita(paciente_sintetico, profesional, inicio, 60, "Reprogramada"), "P F", "s"
            )
    finally:
        _borrar_agendas(cliente_firestore, profesional)


def test_odontograma_actualiza_solo_la_pieza(unidad_firestore, paciente_sintetico):
    from app.domain.odontograma import EstadoPieza, Superficie

    ahora = datetime.now(UTC)
    with unidad_firestore() as unidad:
        unidad.odontograma.actualizar_pieza(
            paciente_sintetico,
            EstadoPieza("36", EstadoDental.CARIES, "p", ahora, (Superficie.OCLUSAL,)),
        )
        unidad.odontograma.actualizar_pieza(
            paciente_sintetico, EstadoPieza("11", EstadoDental.SANA, "p", ahora)
        )
        unidad.commit()
    with unidad_firestore() as unidad:
        unidad.odontograma.actualizar_pieza(
            paciente_sintetico, EstadoPieza("36", EstadoDental.OBTURADA, "p", ahora, nota="Resina")
        )
        unidad.commit()
        odontograma = unidad.odontograma.obtener(paciente_sintetico)
    assert set(odontograma.piezas) == {"11", "36"}
    assert odontograma.piezas["36"].estado == "obturada"
    assert odontograma.piezas["36"].superficies == ()


def test_busqueda_por_nombre_en_firestore(cliente_firestore, unidad_firestore):
    """Regla comun: comienzo de palabra, sin acentos ni mayusculas; incluye archivados."""
    from app.domain import busqueda

    marca = "Zzprueba" + date.today().strftime("%d%H%M%S")
    ids = []
    with unidad_firestore() as unidad:
        for nombres, apellidos in ((f"{marca} María", "Pérez"), (f"{marca} Marco", "Perera")):
            ids.append(unidad.pacientes.registrar(NuevoPaciente(nombres, apellidos)).id_paciente)
        unidad.commit()
    try:
        with unidad_firestore() as unidad:
            ambos = unidad.pacientes.buscar(busqueda.palabras(f"{marca} mar"), 10)
            uno = unidad.pacientes.buscar(busqueda.palabras(f"{marca} MARÍA perez"), 10)
            ninguno = unidad.pacientes.buscar(busqueda.palabras(f"{marca} xyz"), 10)
            limitado = unidad.pacientes.buscar(busqueda.palabras(marca), 1)
        assert {p.id_paciente for p in ambos} == set(ids)
        assert [p.apellidos for p in ambos] == ["Perera", "Pérez"]  # apellidos, nombres
        assert [p.id_paciente for p in uno] == [ids[0]]
        assert ninguno == []
        assert len(limitado) == 1
    finally:
        for identificador in ids:
            _borrar_paciente(cliente_firestore, identificador)


# --- Adendas, correccion de datos y citas confirmadas ---


def _consulta_base(unidad_firestore, id_paciente):
    from app.domain.consulta import Diagnostico, NuevaConsulta

    with unidad_firestore() as unidad:
        creada = unidad.historial.registrar_consulta(
            id_paciente,
            "00000000-0000-0000-0000-000000000000",
            NuevaConsulta("Dolor", notas="Primera", diagnosticos=(Diagnostico("Caries"),)),
        )
        unidad.commit()
    return creada.id_consulta


def test_adenda_agrega_sin_reemplazar_y_se_lee(unidad_firestore, paciente_sintetico):
    from app.domain.consulta import Adenda, Diagnostico, Receta, Tratamiento
    from app.domain.errores import ConsultaNoEncontrada

    id_consulta = _consulta_base(unidad_firestore, paciente_sintetico)
    adenda = Adenda(
        nota="Radiografia revisada",
        diagnosticos=(Diagnostico("Pulpitis", "K04", "CIE-10"),),
        tratamientos=(Tratamiento("Endodoncia"),),
        recetas=(Receta("Amoxicilina", "500 mg", "c/8h"),),
    )
    with unidad_firestore() as unidad:
        devuelta = unidad.historial.agregar_a_consulta(
            paciente_sintetico, id_consulta, "profesional-1", adenda
        )
        leida = unidad.historial.obtener_consulta(paciente_sintetico, id_consulta)
        assert unidad.historial.obtener_consulta(paciente_sintetico, "no-existe") is None
        assert unidad.historial.obtener_consulta("a/b", id_consulta) is None
        with pytest.raises(ConsultaNoEncontrada):
            unidad.historial.agregar_a_consulta(
                paciente_sintetico, "no-existe", "profesional-1", adenda
            )
    assert leida == devuelta
    assert [d.descripcion for d in leida.diagnosticos] == ["Caries", "Pulpitis"]
    assert leida.notas.startswith("Primera\n\n[Adenda ") and "profesional-1" in leida.notas
    assert leida.recetas[0].medicamento == "Amoxicilina"


def _solo_en_proyecto_real():
    # El emulador 1.19.8 no conserva el turno de una transaccion al reintentar: con varias
    # sobre el mismo documento se abortan todas. El servicio real si resuelve la contencion.
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("El emulador no resuelve la contencion entre transacciones.")


def test_adendas_simultaneas_no_se_pierden_en_firestore(unidad_firestore, paciente_sintetico):
    from app.domain.consulta import Adenda, Diagnostico

    _solo_en_proyecto_real()
    id_consulta = _consulta_base(unidad_firestore, paciente_sintetico)
    errores = []

    def agregar(n):
        try:
            with unidad_firestore() as unidad:
                unidad.historial.agregar_a_consulta(
                    paciente_sintetico,
                    id_consulta,
                    "p",
                    Adenda(diagnosticos=(Diagnostico(f"Dx {n}"),)),
                )
        except Exception as error:  # noqa: BLE001 - se reporta en la asercion
            errores.append(error)

    hilos = [threading.Thread(target=agregar, args=(n,)) for n in range(4)]
    [h.start() for h in hilos]
    [h.join(timeout=60) for h in hilos]
    with unidad_firestore() as unidad:
        leida = unidad.historial.obtener_consulta(paciente_sintetico, id_consulta)
    assert errores == [] and len(leida.diagnosticos) == 5


def test_corregir_datos_alergias_y_busqueda_con_el_nombre_nuevo(
    cliente_firestore, unidad_firestore, paciente_sintetico
):
    from app.domain import busqueda
    from app.domain.errores import DatosInvalidos, PacienteArchivado
    from app.domain.paciente import Alergia, Baja, CambiosPaciente, Contacto, MotivoBaja

    with unidad_firestore() as unidad:
        unidad.pacientes.actualizar(
            paciente_sintetico,
            CambiosPaciente(
                nombres="Zzcorregido Maria",
                fecha_nacimiento=date(2001, 4, 5),
                contacto=Contacto(correo="nuevo@example.invalid"),
            ),
        )
        unidad.pacientes.agregar_alergias(paciente_sintetico, (Alergia("Polen", "Tos"),))
    with unidad_firestore() as unidad:
        p = unidad.pacientes.obtener_por_id(paciente_sintetico)
        assert (p.nombres, p.fecha_nacimiento) == ("Zzcorregido Maria", date(2001, 4, 5))
        assert p.contacto == Contacto(None, "nuevo@example.invalid", None)
        assert [a.sustancia for a in p.alergias] == ["Latex", "Polen"]
        assert [
            x.id_paciente for x in unidad.pacientes.buscar(busqueda.palabras("zzcorreg"), 5)
        ] == [paciente_sintetico]
        with pytest.raises(DatosInvalidos):
            unidad.pacientes.agregar_alergias(paciente_sintetico, (Alergia("LATEX"),))
        with pytest.raises(DatosInvalidos):
            unidad.pacientes.actualizar(
                paciente_sintetico, CambiosPaciente(fecha_nacimiento=date.today() + timedelta(1))
            )
        unidad.pacientes.archivar(
            paciente_sintetico, Baja(MotivoBaja.TRASLADO, "p", datetime.now(UTC))
        )
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.actualizar(paciente_sintetico, CambiosPaciente(nombres="X"))
        with pytest.raises(PacienteArchivado):
            unidad.pacientes.agregar_alergias(paciente_sintetico, (Alergia("Nueva"),))


def test_cita_confirmada_ocupa_y_atendida_libera(
    cliente_firestore, unidad_firestore, paciente_sintetico
):
    from app.domain.cita import EstadoCita, NuevaCita
    from app.domain.errores import ConflictoAgenda, PacienteArchivado
    from app.domain.paciente import Baja, MotivoBaja

    profesional = f"prueba-{uuid4()}"
    inicio = datetime(2030, 2, 15, 15, 0, tzinfo=UTC)
    try:
        with unidad_firestore() as unidad:
            cita = unidad.citas.agendar(
                NuevaCita(paciente_sintetico, profesional, inicio, 30, "x"), "P F", "s"
            )
            unidad.citas.cambiar_estado(cita.id_cita, EstadoCita.CONFIRMADA, "s", None)
            with pytest.raises(ConflictoAgenda):  # confirmada sigue ocupando
                unidad.citas.agendar(
                    NuevaCita(paciente_sintetico, profesional, inicio, 30, "y"), "P F", "s"
                )
            unidad.citas.cambiar_estado(cita.id_cita, EstadoCita.ATENDIDA, "s", None)
            unidad.citas.agendar(  # atendida libera el horario
                NuevaCita(paciente_sintetico, profesional, inicio, 30, "z"), "P F", "s"
            )
            unidad.pacientes.archivar(
                paciente_sintetico, Baja(MotivoBaja.TRASLADO, "p", datetime.now(UTC))
            )
            with pytest.raises(PacienteArchivado):
                unidad.citas.agendar(
                    NuevaCita(
                        paciente_sintetico, profesional, inicio + timedelta(hours=3), 30, "w"
                    ),
                    "P F",
                    "s",
                )
    finally:
        _borrar_agendas(cliente_firestore, profesional)


def _borrar_agendas(cliente, profesional):
    for agenda in (
        cliente.collection("agendas")
        .where(filter=FieldFilter("id_profesional", "==", profesional))
        .stream()
    ):
        agenda.reference.delete()


# --- Concurrencia: dos usuarios a la vez sobre el mismo dato ---


def _simultaneos(*operaciones):
    """Ejecuta cada operacion en su hilo y devuelve el resultado o el error de cada una."""
    barrera = threading.Barrier(len(operaciones))
    resultados = [None] * len(operaciones)

    def correr(indice, operacion):
        barrera.wait(timeout=30)
        try:
            resultados[indice] = operacion()
        except Exception as error:  # noqa: BLE001 - la prueba compara el tipo de error
            resultados[indice] = error

    hilos = [threading.Thread(target=correr, args=par) for par in enumerate(operaciones)]
    [h.start() for h in hilos]
    [h.join(timeout=120) for h in hilos]
    return resultados


def test_dos_citas_simultaneas_una_sola_reserva(
    cliente_firestore, unidad_firestore, paciente_sintetico
):
    from app.domain.cita import NuevaCita
    from app.domain.errores import ConflictoAgenda

    _solo_en_proyecto_real()
    profesional = f"prueba-{uuid4()}"
    inicio = datetime(2030, 3, 15, 15, 0, tzinfo=UTC)

    def reservar(motivo):
        def operacion():
            with unidad_firestore() as unidad:
                return unidad.citas.agendar(
                    NuevaCita(paciente_sintetico, profesional, inicio, 30, motivo), "P F", "s"
                )

        return operacion

    try:
        resultados = _simultaneos(*(reservar(f"Cita {n}") for n in range(4)))
        errores = [r for r in resultados if isinstance(r, Exception)]
        assert len(resultados) - len(errores) == 1, resultados
        assert all(isinstance(e, ConflictoAgenda) for e in errores), errores
        with unidad_firestore() as unidad:
            agenda = unidad.citas.listar_agenda(
                inicio - timedelta(hours=1), inicio + timedelta(hours=1), profesional
            )
        assert len(agenda) == 1
    finally:
        _borrar_agendas(cliente_firestore, profesional)


def test_dos_bajas_simultaneas_solo_una_gana(unidad_firestore, paciente_sintetico):
    from app.domain.errores import PacienteArchivado
    from app.domain.paciente import Baja, MotivoBaja

    _solo_en_proyecto_real()

    def archivar(profesional):
        def operacion():
            with unidad_firestore() as unidad:
                unidad.pacientes.archivar(
                    paciente_sintetico, Baja(MotivoBaja.TRASLADO, profesional, datetime.now(UTC))
                )
                return "archivado"

        return operacion

    resultados = _simultaneos(archivar("a"), archivar("b"))
    assert sorted(type(r).__name__ for r in resultados) == ["PacienteArchivado", "str"]
    assert any(isinstance(r, PacienteArchivado) for r in resultados)


def test_consulta_contra_baja_no_deja_consulta_en_archivado(unidad_firestore, paciente_sintetico):
    from app.domain.consulta import NuevaConsulta
    from app.domain.errores import PacienteArchivado
    from app.domain.paciente import Baja, MotivoBaja

    _solo_en_proyecto_real()

    def registrar():
        with unidad_firestore() as unidad:
            return unidad.historial.registrar_consulta(
                paciente_sintetico, "p", NuevaConsulta("Carrera")
            )

    def archivar():
        with unidad_firestore() as unidad:
            unidad.pacientes.archivar(
                paciente_sintetico, Baja(MotivoBaja.TRASLADO, "p", datetime.now(UTC))
            )
            return "archivado"

    consulta, baja = _simultaneos(registrar, archivar)
    assert baja == "archivado"
    # Vale cualquier orden, pero la consulta o entro antes de la baja o se rechazo.
    assert isinstance(consulta, PacienteArchivado) or consulta.motivo == "Carrera"
    with unidad_firestore() as unidad:
        guardadas = unidad.historial.listar_consultas(paciente_sintetico, 5)
        assert unidad.pacientes.obtener_por_id(paciente_sintetico).archivado
    assert len(guardadas) == (0 if isinstance(consulta, PacienteArchivado) else 1)


def test_pieza_de_historial_archivado_se_rechaza_en_el_adaptador(
    unidad_firestore, paciente_sintetico
):
    """Sin pasar por el caso de uso: la regla la sostiene la transaccion del motor."""
    from app.domain.errores import PacienteArchivado, PacienteNoEncontrado
    from app.domain.odontograma import EstadoPieza
    from app.domain.paciente import Baja, MotivoBaja

    pieza = EstadoPieza("36", EstadoDental.CARIES, "p", datetime.now(UTC))
    with unidad_firestore() as unidad:
        with pytest.raises(PacienteNoEncontrado):
            unidad.odontograma.actualizar_pieza("no-existe", pieza)
        with pytest.raises(PacienteNoEncontrado):
            unidad.odontograma.actualizar_pieza("a/b", pieza)
        unidad.pacientes.archivar(
            paciente_sintetico, Baja(MotivoBaja.TRASLADO, "p", datetime.now(UTC))
        )
        with pytest.raises(PacienteArchivado):
            unidad.odontograma.actualizar_pieza(paciente_sintetico, pieza)
        assert unidad.odontograma.obtener(paciente_sintetico).piezas == {}


def test_piezas_simultaneas_no_se_pisan(unidad_firestore, paciente_sintetico):
    from app.domain.odontograma import EstadoPieza

    _solo_en_proyecto_real()

    def guardar(codigo):
        def operacion():
            with unidad_firestore() as unidad:
                unidad.odontograma.actualizar_pieza(
                    paciente_sintetico,
                    EstadoPieza(codigo, EstadoDental.SANA, "p", datetime.now(UTC)),
                )
                return codigo

        return operacion

    codigos = ["11", "12", "21", "22"]
    assert sorted(_simultaneos(*(guardar(c) for c in codigos))) == codigos
    with unidad_firestore() as unidad:
        assert set(unidad.odontograma.obtener(paciente_sintetico).piezas) == set(codigos)


# --- Flujo por HTTP: las pantallas de la clinica contra el adaptador real ---


@pytest.fixture
def api_clinica(cliente_firestore, settings):
    from fastapi.testclient import TestClient

    from app.bootstrap.container import Contenedor
    from app.domain import permisos
    from app.domain.identidad import UsuarioAutenticado
    from app.domain.institucion import Institucion
    from app.domain.profesional import ProfesionalLocal
    from app.infrastructure.persistence.firestore.unidad import UnidadTrabajoFirestore
    from app.main import create_app
    from tests.doubles import AutenticadorDoble

    clinica = Institucion.CLINICA_ODONTOLOGICA
    odontologo = f"prueba-{uuid4()}"
    secretaria = f"prueba-{uuid4()}"
    contenedor = Contenedor(
        autenticador=AutenticadorDoble(
            {
                "sec": UsuarioAutenticado(
                    secretaria, clinica, permisos.PERMISOS_POR_ROL["secretaria"]
                ),
                "odo": UsuarioAutenticado(
                    odontologo,
                    clinica,
                    permisos.PERMISOS_POR_ROL["odontologo"] | {permisos.HISTORIALES_ARCHIVAR},
                ),
            }
        ),
        unidades_trabajo={clinica: lambda: UnidadTrabajoFirestore(cliente_firestore)},
    )
    with UnidadTrabajoFirestore(cliente_firestore) as unidad:
        unidad.profesionales.sincronizar(ProfesionalLocal(odontologo, "Odo", "Zz", "odontologo"))
        unidad.profesionales.sincronizar(ProfesionalLocal(secretaria, "Sec", "Zz", "secretaria"))
        unidad.commit()
    pacientes = []
    try:
        with TestClient(create_app(settings, contenedor)) as cliente:
            yield cliente, odontologo, pacientes
    finally:
        for identificador in pacientes:
            _borrar_paciente(cliente_firestore, identificador)
        _borrar_agendas(cliente_firestore, odontologo)
        for identificador in (odontologo, secretaria):
            cliente_firestore.collection("profesionales").document(identificador).delete()


def test_recorrido_de_secretaria_y_odontologo_por_http(api_clinica):
    cliente, odontologo, pacientes = api_clinica
    sec = {"Authorization": "Bearer sec"}
    odo = {"Authorization": "Bearer odo"}
    base = "/api/v1/pacientes"

    # Secretaria: registrar (con alergia que luego no ve), buscar, editar y agendar.
    alta = cliente.post(
        base,
        json={
            "nombres": "Zzficha Diego",
            "apellidos": "Oliva",
            "fecha_nacimiento": "1992-04-17",
            "contacto": {"telefono": "0000-0000"},
            "alergias": [{"sustancia": "Latex", "severidad": "Moderada"}],
        },
        headers=sec,
    )
    assert alta.status_code == 201
    id_paciente = alta.json()["id_paciente"]
    pacientes.append(id_paciente)
    assert alta.json()["alergias"] is None
    encontrados = cliente.get(base, params={"nombre": "zzficha oliva"}, headers=sec).json()
    assert [p["id_paciente"] for p in encontrados] == [id_paciente]
    assert encontrados[0]["archivado"] is False
    editado = cliente.patch(
        f"{base}/{id_paciente}",
        json={"contacto": {"correo": "x@example.invalid", "telefono": None, "direccion": None}},
        headers=sec,
    )
    assert editado.json()["contacto"]["telefono"] is None
    assert (
        cliente.post(
            f"{base}/{id_paciente}/alergias",
            json={"alergias": [{"sustancia": "Latex"}]},
            headers=sec,
        ).status_code
        == 403
    )
    assert cliente.get(f"{base}/{id_paciente}/historial", headers=sec).status_code == 403
    assert cliente.get(f"{base}/{id_paciente}/odontograma", headers=sec).status_code == 403

    inicio = datetime(2030, 4, 1, 15, 0, tzinfo=UTC)
    cita = {
        "id_paciente": id_paciente,
        "id_profesional": odontologo,
        "inicio": inicio.isoformat(),
        "duracion_minutos": 30,
        "motivo": "Control",
    }
    agendada = cliente.post("/api/v1/citas", json=cita, headers=sec)
    assert agendada.status_code == 201
    assert agendada.json()["nombre_paciente"] == "Zzficha Diego Oliva"
    assert cliente.post("/api/v1/citas", json=cita, headers=sec).status_code == 409
    semana = cliente.get(
        "/api/v1/citas",
        params={
            "desde": inicio.isoformat(),
            "hasta": (inicio + timedelta(days=7)).isoformat(),
            "id_profesional": odontologo,
        },
        headers=sec,
    )
    assert [c["id_cita"] for c in semana.json()] == [agendada.json()["id_cita"]]
    del_paciente = cliente.get(f"{base}/{id_paciente}/citas", headers=sec)
    assert del_paciente.json()[0]["estado"] == "programada"

    # Odontologo: ve alergias, registra consulta y adenda, y cambia piezas.
    ficha = cliente.get(f"{base}/{id_paciente}", headers=odo).json()
    assert ficha["alergias"][0]["sustancia"] == "Latex"
    consulta = cliente.post(
        f"{base}/{id_paciente}/consultas",
        json={
            "motivo": "Dolor",
            "notas": "Sensibilidad en pieza 37.",
            "diagnosticos": [{"descripcion": "Caries", "codigo": "K02.1"}],
            "tratamientos": [{"descripcion": "Obturacion"}],
            "recetas": [{"medicamento": "Ibuprofeno", "dosis": "1", "frecuencia": "c/8h"}],
        },
        headers=odo,
    )
    assert consulta.status_code == 201
    adenda = cliente.post(
        f"{base}/{id_paciente}/consultas/{consulta.json()['id_consulta']}/adenda",
        json={"nota": "Radiografia revisada"},
        headers=odo,
    )
    assert "[Adenda " in adenda.json()["notas"]
    historial = cliente.get(f"{base}/{id_paciente}/historial", params={"limite": 1}, headers=odo)
    assert historial.json()["consultas"][0]["motivo"] == "Dolor"
    pieza = cliente.put(
        f"{base}/{id_paciente}/odontograma/piezas/37",
        json={"estado": "caries", "superficies": ["oclusal"], "nota": "Lesion"},
        headers=odo,
    )
    assert pieza.status_code == 200
    cliente.put(
        f"{base}/{id_paciente}/odontograma/piezas/55",
        json={"estado": "en_erupcion"},
        headers=odo,
    )
    odontograma = cliente.get(f"{base}/{id_paciente}/odontograma", headers=odo).json()
    assert [p["pieza"] for p in odontograma["piezas"]] == ["37", "55"]
    assert odontograma["piezas"][0]["actualizado_por"] == odontologo

    # Archivar: se conserva todo, pero ya no admite nada nuevo.
    assert (
        cliente.post(
            f"{base}/{id_paciente}/archivo",
            json={"motivo": "traslado", "detalle": "Otra clinica"},
            headers=odo,
        ).status_code
        == 200
    )
    assert cliente.get(f"{base}/{id_paciente}", headers=sec).json()["archivado"] is True
    rechazos = [
        cliente.put(
            f"{base}/{id_paciente}/odontograma/piezas/11", json={"estado": "sana"}, headers=odo
        ),
        cliente.post(f"{base}/{id_paciente}/consultas", json={"motivo": "x"}, headers=odo),
        cliente.patch(f"{base}/{id_paciente}", json={"nombres": "X"}, headers=sec),
        cliente.post(
            "/api/v1/citas",
            json={**cita, "inicio": (inicio + timedelta(hours=2)).isoformat()},
            headers=sec,
        ),
    ]
    assert [r.status_code for r in rechazos] == [409, 409, 409, 409]
    # Una cita ya agendada se puede cancelar aunque el historial este archivado.
    cancelada = cliente.post(
        f"/api/v1/citas/{agendada.json()['id_cita']}/estado",
        json={"estado": "cancelada", "motivo": "Traslado"},
        headers=sec,
    )
    assert cancelada.json()["motivo_cambio"] == "Traslado"
