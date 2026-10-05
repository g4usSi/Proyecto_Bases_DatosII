import psycopg
import pymysql
from pymongo import MongoClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.institucion import Institucion
from app.infrastructure.identity.jwt import AutenticadorCentral
from app.infrastructure.identity.postgresql import DirectorioPostgreSQL
from app.infrastructure.persistence.mongodb.lectura import UnidadTrabajoLecturaMongo
from app.infrastructure.persistence.sql import UnidadTrabajoSQL


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
        contenedor.unidades_trabajo[Institucion.HOSPITAL_GENERAL] = lambda: UnidadTrabajoSQL(
            lambda: psycopg.connect(dsn, connect_timeout=5),
            "SELECT id_paciente, nombres, apellidos, fecha_nacimiento "
            "FROM public.paciente WHERE id_paciente = %s",
            (psycopg.Error,),
        )
    if settings.mysql_host and settings.mysql_password:
        contenedor.unidades_trabajo[Institucion.CENTRO_PEDIATRICO] = lambda: UnidadTrabajoSQL(
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
            ),
            "SELECT id_paciente, nombre, apellido, fecha_nacimiento "
            "FROM paciente WHERE id_paciente = %s",
            (pymysql.MySQLError,),
        )
    if settings.mongodb_uri:
        cliente = MongoClient(
            settings.mongodb_uri.get_secret_value(), serverSelectionTimeoutMS=5000
        )
        contenedor.cierres.append(cliente.close)
        contenedor.unidades_trabajo[Institucion.LABORATORIO_CLINICO] = lambda: (
            UnidadTrabajoLecturaMongo(cliente[settings.mongodb_database])
        )
    return contenedor
