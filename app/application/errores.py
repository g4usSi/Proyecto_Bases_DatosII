class IntegracionNoConfigurada(Exception):
    """El esqueleto aun no tiene conectado el adaptador solicitado (HTTP 503)."""


class OperacionPendiente(Exception):
    """El motor de la institucion aun no implementa esta operacion (HTTP 501).

    Cada rama de motor reemplaza los metodos que lanzan este error por la
    implementacion real. Asi la API completa existe desde el principio y se ve
    claramente que falta en cada motor.
    """
