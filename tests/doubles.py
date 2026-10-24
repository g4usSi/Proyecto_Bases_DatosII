from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Literal, Self

from app.domain import busqueda
from app.domain.cita import Cita, EstadoCita, NuevaCita
from app.domain.consulta import Consulta, NuevaConsulta
from app.domain.errores import ConflictoAgenda, TokenInvalido
from app.domain.identidad import UsuarioAutenticado
from app.domain.odontograma import EstadoPieza, Odontograma
from app.domain.paciente import Baja, NuevoPaciente, Paciente
from app.domain.profesional import ProfesionalLocal


@dataclass
class AutenticadorDoble:
    usuarios: dict[str, UsuarioAutenticado]

    def verificar_token(self, token: str) -> UsuarioAutenticado:
        usuario = self.usuarios.get(token)
        if usuario is None:
            raise TokenInvalido("Token de prueba invalido.")
        return usuario


@dataclass
class RepositorioDoble:
    registros: dict[str, Paciente]
    bajas: dict[str, Baja] = field(default_factory=dict)

    def obtener_por_id(self, id_paciente: str) -> Paciente | None:
        return self.registros.get(id_paciente)

    def registrar(self, datos: NuevoPaciente) -> Paciente:
        paciente = Paciente(
            str(len(self.registros) + 1),
            datos.nombres,
            datos.apellidos,
            datos.fecha_nacimiento,
            contacto=datos.contacto,
            alergias=datos.alergias,
        )
        self.registros[paciente.id_paciente] = paciente
        return paciente

    def buscar(self, palabras: tuple[str, ...], limite: int) -> list[Paciente]:
        encontrados = [
            p
            for p in self.registros.values()
            if busqueda.coincide(palabras, p.nombres, p.apellidos)
        ]
        encontrados.sort(key=lambda p: (p.apellidos, p.nombres, p.id_paciente))
        return encontrados[:limite]

    def archivar(self, id_paciente: str, baja: Baja) -> None:
        self.registros[id_paciente] = replace(self.registros[id_paciente], archivado=True)
        self.bajas[id_paciente] = baja


@dataclass
class HistorialDoble:
    consultas: list[Consulta] = field(default_factory=list)

    def listar_consultas(
        self, id_paciente: str, limite: int, antes_de: datetime | None = None
    ) -> list[Consulta]:
        filas = sorted(
            (c for c in self.consultas if c.id_paciente == id_paciente),
            key=lambda c: c.fecha_hora,
            reverse=True,
        )
        if antes_de is not None:
            filas = [c for c in filas if c.fecha_hora < antes_de]
        return filas[:limite]

    def registrar_consulta(
        self, id_paciente: str, id_profesional: str, datos: NuevaConsulta
    ) -> Consulta:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        consulta = Consulta(
            str(len(self.consultas) + 1),
            id_paciente,
            id_profesional,
            base + timedelta(hours=len(self.consultas)),
            datos.motivo,
            datos.notas,
            datos.diagnosticos,
            datos.tratamientos,
            datos.recetas,
        )
        self.consultas.append(consulta)
        return consulta


@dataclass
class ProfesionalesDoble:
    registros: dict[str, ProfesionalLocal] = field(default_factory=dict)

    def obtener(self, id_profesional: str) -> ProfesionalLocal | None:
        return self.registros.get(id_profesional)


@dataclass
class CitasDoble:
    registros: dict[str, Cita] = field(default_factory=dict)

    def obtener(self, id_cita: str) -> Cita | None:
        return self.registros.get(id_cita)

    def agendar(self, datos: NuevaCita, nombre_paciente: str, creada_por: str) -> Cita:
        for cita in self.registros.values():
            if (
                cita.estado == EstadoCita.PROGRAMADA
                and cita.id_profesional == datos.id_profesional
                and cita.inicio < datos.fin
                and datos.inicio < cita.fin
            ):
                raise ConflictoAgenda("Horario ocupado.")
        cita = Cita(
            str(len(self.registros) + 1),
            datos.id_paciente,
            nombre_paciente,
            datos.id_profesional,
            datos.inicio,
            datos.fin,
            datos.motivo,
            EstadoCita.PROGRAMADA,
            creada_por,
        )
        self.registros[cita.id_cita] = cita
        return cita

    def listar_agenda(
        self, desde: datetime, hasta: datetime, id_profesional: str | None = None
    ) -> list[Cita]:
        return sorted(
            (
                c
                for c in self.registros.values()
                if desde <= c.inicio < hasta
                and (id_profesional is None or c.id_profesional == id_profesional)
            ),
            key=lambda c: c.inicio,
        )

    def listar_por_paciente(self, id_paciente: str, limite: int) -> list[Cita]:
        filas = [c for c in self.registros.values() if c.id_paciente == id_paciente]
        return sorted(filas, key=lambda c: c.inicio, reverse=True)[:limite]

    def cambiar_estado(
        self, id_cita: str, estado: EstadoCita, por: str, motivo: str | None
    ) -> Cita:
        cita = replace(self.registros[id_cita], estado=estado, motivo_cambio=motivo)
        self.registros[id_cita] = cita
        return cita


@dataclass
class OdontogramaDoble:
    piezas: dict[str, dict[str, EstadoPieza]] = field(default_factory=dict)

    def obtener(self, id_paciente: str) -> Odontograma:
        return Odontograma(id_paciente, dict(self.piezas.get(id_paciente, {})))

    def actualizar_pieza(self, id_paciente: str, estado: EstadoPieza) -> None:
        self.piezas.setdefault(id_paciente, {})[estado.pieza] = estado


class UnidadTrabajoDoble:
    def __init__(
        self,
        registros: dict[str, Paciente],
        historial: HistorialDoble | None = None,
        profesionales: dict[str, ProfesionalLocal] | None = None,
    ) -> None:
        self.pacientes = RepositorioDoble(registros)
        self.historial = historial if historial is not None else HistorialDoble()
        self.profesionales = ProfesionalesDoble(profesionales or {})
        self.citas = CitasDoble()
        self.odontograma = OdontogramaDoble()
        self.confirmaciones = 0
        self.reversiones = 0
        self.finalizada = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        self.rollback()
        self.finalizada = True
        return False

    def commit(self) -> None:
        self.confirmaciones += 1

    def rollback(self) -> None:
        self.reversiones += 1
