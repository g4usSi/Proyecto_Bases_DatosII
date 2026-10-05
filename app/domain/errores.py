class ErrorDominio(Exception):
    """Error de negocio que la capa HTTP traduce a una respuesta."""


class PacienteNoEncontrado(ErrorDominio):
    pass


class AccesoDenegado(ErrorDominio):
    pass


class TokenInvalido(ErrorDominio):
    pass
