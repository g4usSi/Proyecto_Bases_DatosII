import logging
from zoneinfo import ZoneInfo

import pymysql
from pymongo import MongoClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.institucion import Institucion
from app.infrastructure.identity.jwt import AutenticadorCentral
from app.infrastructure.identity.postgresql import DirectorioPostgreSQL
from app.infrastructure.persistence.mongodb.unidad import UnidadTrabajoMongo
from app.infrastructure.persistence.mysql.unidad import UnidadTrabajoMySQL
from app.infrastructure.persistence.postgresql.unidad import UnidadTrabajoPostgreSQL

logger = logging.getLogger(__name__)


def crear_contenedor(settings: Settings) -> Contenedor:
    contenedor = Contenedor()
    if settings.postgres_dsn and settings.jwt_secret:
        dsn = settings.postgres_dsn.get_secret_value()
        autenticador = AutenticadorCentral(
            DirectorioPostgreSQL(dsn),
            settings.jwt_secret.get_secret_value(),
            settings.jwt_issuer,
            settings.jwt_audience,
            settings.access_token_minutes,
        )
        contenedor.autenticador = autenticador
        contenedor.inicio_sesion = autenticador
        contenedor.unidades_trabajo[Institucion.HOSPITAL_GENERAL] = lambda: UnidadTrabajoPostgreSQL(
            dsn
        )
    if settings.mysql_host and settings.mysql_password:
        contenedor.unidades_trabajo[Institucion.CENTRO_PEDIATRICO] = lambda: UnidadTrabajoMySQL(
            lambda: pymysql.connect(
                host=settings.mysql_host,
                port=settings.mysql_port,
                user=settings.mysql_user,
                password=settings.mysql_password.get_secret_value(),
                database=settings.mysql_database,
                charset="utf8mb4",
                connect_timeout=5,
                read_timeout=10,
                write_timeout=10,
                init_command="SET time_zone = '+00:00'",
            )
        )
    if settings.mongodb_uri:
        cliente = MongoClient(
            settings.mongodb_uri.get_secret_value(), serverSelectionTimeoutMS=5000
        )
        contenedor.cierres.append(cliente.close)
        contenedor.unidades_trabajo[Institucion.LABORATORIO_CLINICO] = lambda: UnidadTrabajoMongo(
            cliente[settings.mongodb_database]
        )
    registrar_firestore(contenedor, settings)
    return contenedor


def registrar_firestore(contenedor: Contenedor, settings: Settings) -> None:
    ruta = settings.firestore_credentials
    if ruta is None:
        return
    if not ruta.is_file():
        # Un companero sin la clave puede trabajar con los otros tres motores.
        logger.warning(
            "No se encontro la clave de Firebase en %s; la clinica odontologica respondera 503.",
            ruta,
        )
        return
    # Importacion tardia: el SDK de Google solo se carga si Firestore esta configurado.
    from app.infrastructure.persistence.firestore.cliente import crear_cliente_firestore
    from app.infrastructure.persistence.firestore.unidad import UnidadTrabajoFirestore

    cliente, cerrar = crear_cliente_firestore(
        ruta, settings.firestore_project_id, settings.firestore_database
    )
    contenedor.cierres.append(cerrar)
    zona = ZoneInfo(settings.zona_horaria)
    contenedor.unidades_trabajo[Institucion.CLINICA_ODONTOLOGICA] = lambda: UnidadTrabajoFirestore(
        cliente, zona
    )
    logger.info("Firestore conectado para la clinica odontologica (proyecto %s).", cliente.project)
