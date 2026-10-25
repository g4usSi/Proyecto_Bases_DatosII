"""Bitacora de accesos a informacion clinica (logger "auditoria").

Registra QUIEN (usuario y institucion), QUE (metodo y ruta con parametros sin sustituir,
permiso exigido) y SOBRE QUE paciente. Nunca escribe datos clinicos ni el cuerpo de la
solicitud. Un acceso denegado se registra como advertencia.
"""

import logging

from app.domain.identidad import UsuarioAutenticado

logger = logging.getLogger("auditoria")


def _linea(
    evento: str,
    usuario: UsuarioAutenticado,
    metodo: str,
    ruta: str,
    permiso: str,
    paciente: str | None,
) -> str:
    return (
        f"evento={evento} usuario={usuario.id_usuario} institucion={usuario.institucion.value} "
        f"metodo={metodo} ruta={ruta} permiso={permiso} paciente={paciente or '-'}"
    )


def acceso(
    usuario: UsuarioAutenticado, metodo: str, ruta: str, permiso: str, paciente: str | None
) -> None:
    logger.info(_linea("acceso", usuario, metodo, ruta, permiso, paciente))


def denegado(
    usuario: UsuarioAutenticado, metodo: str, ruta: str, permiso: str, paciente: str | None
) -> None:
    logger.warning(_linea("acceso_denegado", usuario, metodo, ruta, permiso, paciente))
