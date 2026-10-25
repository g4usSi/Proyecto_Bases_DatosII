"""Ordenes de laboratorio (Laboratorio Clinico, MongoDB).

Una orden guarda COPIA de la prueba (nombre, version y parametros con su rango de
referencia): si el catalogo cambia despues, un resultado ya registrado no se reinterpreta.
Estados: solicitada -> en_proceso -> validada. Una orden validada ya no se modifica;
una cancelada tampoco. Se puede cancelar mientras no este validada.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain.errores import DatosInvalidos


class TipoValor(StrEnum):
    NUMERICO = "numerico"
    TEXTO = "texto"
    BOOLEANO = "booleano"


class EstadoOrden(StrEnum):
    SOLICITADA = "solicitada"
    EN_PROCESO = "en_proceso"
    VALIDADA = "validada"
    CANCELADA = "cancelada"


ESTADOS_ABIERTOS = frozenset({EstadoOrden.SOLICITADA, EstadoOrden.EN_PROCESO})

Valor = float | int | str | bool


@dataclass(frozen=True, slots=True)
class Referencia:
    minimo: float | None = None
    maximo: float | None = None
    descripcion: str | None = None
    poblacion: str | None = None


@dataclass(frozen=True, slots=True)
class ParametroPrueba:
    codigo: str
    nombre: str
    tipo_valor: TipoValor
    unidad: str | None = None
    referencia: Referencia | None = None


@dataclass(frozen=True, slots=True)
class PruebaCatalogo:
    codigo: str
    nombre: str
    version: int
    parametros: tuple[ParametroPrueba, ...]
    tipo_muestra: str | None = None
    indicaciones: str | None = None


@dataclass(frozen=True, slots=True)
class Resultado:
    codigo: str
    nombre: str
    tipo_valor: TipoValor
    valor: Valor
    unidad: str | None = None
    referencia: Referencia | None = None
    interpretacion: str | None = None  # "bajo" | "normal" | "alto" (solo numericos con rango)


@dataclass(frozen=True, slots=True)
class PruebaOrden:
    codigo: str
    nombre: str
    version: int
    parametros: tuple[ParametroPrueba, ...]
    resultados: tuple[Resultado, ...] = field(default_factory=tuple)
    observaciones: str | None = None
    registrado_por: str | None = None
    registrado_en: datetime | None = None


@dataclass(frozen=True, slots=True)
class NuevaMuestra:
    tipo: str
    tomada_en: datetime | None = None
    condicion: str | None = None
    observaciones: str | None = None


@dataclass(frozen=True, slots=True)
class Muestra:
    codigo: str
    tipo: str
    tomada_en: datetime
    condicion: str | None = None
    observaciones: str | None = None


@dataclass(frozen=True, slots=True)
class ValorResultado:
    """Un valor que el laboratorista captura para un parametro de la prueba."""

    codigo_parametro: str
    valor: Valor


@dataclass(frozen=True, slots=True)
class Orden:
    id_orden: str
    numero_orden: str
    id_paciente: str
    id_consulta: str
    id_profesional: str  # quien la solicito
    estado: EstadoOrden
    solicitada_en: datetime
    pruebas: tuple[PruebaOrden, ...]
    muestras: tuple[Muestra, ...] = field(default_factory=tuple)
    validada_en: datetime | None = None
    validada_por: str | None = None
    motivo_cancelacion: str | None = None

    @property
    def lista_para_validar(self) -> bool:
        """Toda prueba pedida tiene al menos un resultado."""
        return bool(self.pruebas) and all(p.resultados for p in self.pruebas)


def interpretar(valor: Valor, referencia: Referencia | None) -> str | None:
    """Compara con el rango del catalogo. Es una ayuda de lectura, no un diagnostico."""
    if referencia is None or isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    if referencia.minimo is not None and valor < referencia.minimo:
        return "bajo"
    if referencia.maximo is not None and valor > referencia.maximo:
        return "alto"
    if referencia.minimo is None and referencia.maximo is None:
        return None
    return "normal"


def construir_resultados(
    prueba: PruebaOrden, valores: tuple[ValorResultado, ...]
) -> tuple[Resultado, ...]:
    """Valida los valores contra los parametros COPIADOS en la orden y calcula la lectura."""
    por_codigo = {p.codigo: p for p in prueba.parametros}
    vistos: set[str] = set()
    resultados = []
    for item in valores:
        parametro = por_codigo.get(item.codigo_parametro)
        if parametro is None:
            raise DatosInvalidos(
                f"'{item.codigo_parametro}' no es un parametro de la prueba {prueba.codigo}."
            )
        if item.codigo_parametro in vistos:
            raise DatosInvalidos(f"El parametro '{item.codigo_parametro}' esta repetido.")
        vistos.add(item.codigo_parametro)
        valor = item.valor
        if parametro.tipo_valor == TipoValor.NUMERICO:
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                raise DatosInvalidos(f"'{parametro.codigo}' requiere un valor numerico.")
        elif parametro.tipo_valor == TipoValor.BOOLEANO:
            if not isinstance(valor, bool):
                raise DatosInvalidos(f"'{parametro.codigo}' requiere verdadero o falso.")
        elif not isinstance(valor, str) or not valor.strip():
            raise DatosInvalidos(f"'{parametro.codigo}' requiere texto.")
        resultados.append(
            Resultado(
                parametro.codigo,
                parametro.nombre,
                parametro.tipo_valor,
                valor,
                parametro.unidad,
                parametro.referencia,
                interpretar(valor, parametro.referencia),
            )
        )
    return tuple(resultados)


@dataclass(frozen=True, slots=True)
class PruebaEnTablero:
    codigo: str
    nombre: str
    version: int
    con_resultados: bool


@dataclass(frozen=True, slots=True)
class ResumenOrden:
    """Una fila del tablero de ordenes de la institucion (sin valores de resultados)."""

    id_orden: str
    numero_orden: str
    id_paciente: str
    nombre_paciente: str
    id_profesional: str
    estado: EstadoOrden
    solicitada_en: datetime
    pruebas: tuple[PruebaEnTablero, ...]
    muestras: int = 0
    validada_en: datetime | None = None

    @property
    def pruebas_pendientes(self) -> int:
        return sum(1 for p in self.pruebas if not p.con_resultados)


@dataclass(frozen=True, slots=True)
class VersionPrueba:
    """Una version publicada de una prueba. Las publicadas no cambian: se agrega otra."""

    prueba: PruebaCatalogo
    activa: bool
    vigente: bool  # la version activa mas reciente: la que usan las ordenes nuevas
