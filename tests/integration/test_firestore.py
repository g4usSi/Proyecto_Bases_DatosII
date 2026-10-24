"""Prueba real contra el proyecto Firebase configurado en .env.

Se ejecuta solo con HISTORIALES_TEST_INTEGRATION=1 y si existe la clave. Crea un
paciente sintetico y lo borra al terminar.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.config import Settings
from app.domain.odontograma import EstadoDental
from app.domain.paciente import NuevoPaciente


@pytest.fixture
def cliente_firestore():
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
        for agenda in (
            cliente_firestore.collection("agendas")
            .where(filter=FieldFilter("id_profesional", "==", profesional))
            .stream()
        ):
            agenda.reference.delete()


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
