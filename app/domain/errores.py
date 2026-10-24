class ErrorDominio(Exception):
    """Error de negocio que la capa HTTP traduce a una respuesta."""


class PacienteNoEncontrado(ErrorDominio):
    pass


class PacienteArchivado(ErrorDominio):
    """El historial esta archivado: se puede leer, pero no modificar."""


class AccesoDenegado(ErrorDominio):
    pass


class TokenInvalido(ErrorDominio):
    pass


class CitaNoEncontrada(ErrorDominio):
    pass


class ConflictoAgenda(ErrorDominio):
    """Horario ocupado o cambio de estado no permitido (HTTP 409)."""


class DatosInvalidos(ErrorDominio):
    """Regla de negocio incumplida por los datos enviados (HTTP 422)."""
