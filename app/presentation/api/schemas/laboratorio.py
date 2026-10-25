from datetime import datetime

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
)

from app.domain.laboratorio import EstadoOrden, TipoValor


class ReferenciaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    minimo: float | None
    maximo: float | None
    descripcion: str | None
    poblacion: str | None


class ParametroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str
    tipo_valor: TipoValor
    unidad: str | None
    referencia: ReferenciaResponse | None


class PruebaCatalogoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str
    version: int
    tipo_muestra: str | None
    indicaciones: str | None
    parametros: list[ParametroResponse]


class OrdenCrear(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id_consulta: str = Field(min_length=1, max_length=128)
    pruebas: list[str] = Field(min_length=1, max_length=50, description="Codigos del catalogo")


class MuestraCrear(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tipo: str = Field(min_length=1, max_length=100, description="p. ej. sangre, orina")
    tomada_en: AwareDatetime | None = Field(default=None, description="Por defecto, ahora")
    condicion: str | None = Field(default=None, min_length=1, max_length=300)
    observaciones: str | None = Field(default=None, min_length=1, max_length=500)


class ValorCrear(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    codigo_parametro: str = Field(min_length=1, max_length=64)
    valor: StrictBool | StrictInt | StrictFloat | StrictStr = Field(
        description="Numero, texto o verdadero/falso segun el tipo del parametro"
    )


class ResultadosCrear(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    valores: list[ValorCrear] = Field(min_length=1, max_length=300)
    observaciones: str | None = Field(default=None, min_length=1, max_length=1000)


class CancelarOrdenCrear(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    motivo: str = Field(min_length=1, max_length=300)


class ResultadoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str
    tipo_valor: TipoValor
    valor: bool | int | float | str
    unidad: str | None
    referencia: ReferenciaResponse | None
    interpretacion: str | None


class PruebaOrdenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    nombre: str
    version: int
    parametros: list[ParametroResponse]
    resultados: list[ResultadoResponse]
    observaciones: str | None
    registrado_por: str | None
    registrado_en: datetime | None


class MuestraResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    tipo: str
    tomada_en: datetime
    condicion: str | None
    observaciones: str | None


class OrdenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_orden: str
    numero_orden: str
    id_paciente: str
    id_consulta: str
    id_profesional: str
    estado: EstadoOrden
    solicitada_en: datetime
    pruebas: list[PruebaOrdenResponse]
    muestras: list[MuestraResponse]
    validada_en: datetime | None
    validada_por: str | None
    motivo_cancelacion: str | None
