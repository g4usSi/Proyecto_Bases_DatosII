"""Busqueda de pacientes por nombre: misma regla en los cuatro motores.

Regla comun: el texto se divide en palabras (separadas por espacios), sin importar
mayusculas ni acentos. Un paciente coincide si CADA palabra buscada es el comienzo
de alguna palabra de "nombres apellidos". Ejemplo: "mar per" encuentra a
"María Pérez López" y "Marco Perera", pero no a "Amaru Pérez".
"""

import unicodedata

MAX_PALABRAS = 5
MAX_LARGO_PALABRA = 50
MIN_LETRAS = 2
LIMITE_PREFIJO = 30


def normalizar(texto: str) -> str:
    """Minusculas y sin acentos (la n con tilde cuenta como n)."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_marcas = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_marcas.casefold()


def palabras(texto: str) -> tuple[str, ...]:
    return tuple(normalizar(texto).split())


def prefijos_de_nombre(nombres: str, apellidos: str) -> list[str]:
    """Todos los comienzos de cada palabra del nombre (para motores sin LIKE, como Firestore)."""
    resultado: set[str] = set()
    for palabra in palabras(f"{nombres} {apellidos}"):
        for largo in range(1, min(len(palabra), LIMITE_PREFIJO) + 1):
            resultado.add(palabra[:largo])
    return sorted(resultado)


def coincide(buscadas: tuple[str, ...], nombres: str, apellidos: str) -> bool:
    """Evalua la regla comun en memoria (Firestore y pruebas)."""
    del_paciente = palabras(f"{nombres} {apellidos}")
    return all(any(p.startswith(b) for p in del_paciente) for b in buscadas)
