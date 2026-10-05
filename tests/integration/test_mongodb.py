from datetime import UTC, datetime
from uuid import uuid4

import pytest
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, WriteError


@pytest.fixture
def laboratorio(config_local):
    cliente = MongoClient(
        host="127.0.0.1",
        port=int(config_local["MONGO_PORT"]),
        username="historiales_admin",
        password=config_local["MONGO_ROOT_PASSWORD"],
        authSource="admin",
    )
    try:
        yield cliente.laboratorio_clinico
    finally:
        cliente.close()


def test_expediente_unico_y_archivo_consistente(laboratorio):
    identificador = ObjectId()
    expediente = uuid4().hex
    documento = {
        "_id": identificador,
        "numero_expediente": expediente,
        "nombres": "Prueba",
        "apellidos": "Sintetica",
        "estado": "Activo",
        "creado_en": datetime.now(UTC),
        "actualizado_en": datetime.now(UTC),
    }
    try:
        laboratorio.pacientes.insert_one(documento)
        with pytest.raises(DuplicateKeyError):
            laboratorio.pacientes.insert_one({**documento, "_id": ObjectId()})
        with pytest.raises(WriteError) as error:
            laboratorio.pacientes.update_one(
                {"_id": identificador}, {"$set": {"estado": "Archivado"}}
            )
        assert error.value.code == 121
        laboratorio.pacientes.update_one(
            {"_id": identificador},
            {
                "$set": {
                    "estado": "Archivado",
                    "fecha_baja": datetime.now(UTC),
                    "motivo_baja": "Prueba",
                }
            },
        )
        assert laboratorio.pacientes.find_one({"_id": identificador})["estado"] == "Archivado"
    finally:
        laboratorio.pacientes.delete_one({"_id": identificador})


def test_orden_validada_requiere_todos_resultados_y_tipos(laboratorio):
    documento = {
        "_id": ObjectId(),
        "numero_orden": uuid4().hex,
        "id_paciente": ObjectId(),
        "id_consulta": ObjectId(),
        "id_profesional_central": str(uuid4()),
        "estado": "Validada",
        "solicitada_en": datetime.now(UTC),
        "validada_en": datetime.now(UTC),
        "validada_por": str(uuid4()),
        "pruebas": [
            {
                "codigo": "A",
                "nombre": "Prueba sintetica",
                "version": 1,
                "resultados": [
                    {"codigo": "P", "nombre": "Parametro", "tipo_valor": "numerico", "valor": 4.2},
                ],
            },
            {"codigo": "B", "nombre": "Segunda prueba", "version": 1, "resultados": []},
        ],
    }
    with pytest.raises(WriteError) as error:
        laboratorio.ordenes_laboratorio.insert_one(documento)
    assert error.value.code == 121
    documento["pruebas"].pop()
    documento["pruebas"][0]["resultados"][0]["valor"] = "no es numero"
    with pytest.raises(WriteError):
        laboratorio.ordenes_laboratorio.insert_one(documento)
    # Estas referencias de prueba muestran que MongoDB NO implementa FKs.
    # No insertar un documento valido con referencias inventadas.
