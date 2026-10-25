from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Literal, Self

from app.domain import busqueda
from app.domain.administracion import EstadoCuenta, FichaProfesional, ProfesionalAgenda
from app.domain.cita import ESTADOS_OCUPAN_HORARIO, Cita, EstadoCita, NuevaCita
from app.domain.consulta import Adenda, Consulta, NuevaConsulta
from app.domain.errores import ConflictoAgenda, ConflictoEstado, TokenInvalido
from app.domain.identidad import UsuarioAutenticado
from app.domain.odontograma import EstadoPieza, Odontograma
from app.domain.paciente import Alergia, Baja, CambiosPaciente, NuevoPaciente, Paciente
from app.domain.profesional import ProfesionalLocal
from app.infrastructure.persistence.pendiente import (
    CobrosNoAplica,
    CrecimientoNoAplica,
    HospitalNoAplica,
    LaboratorioNoAplica,
    TutoresNoAplica,
    VacunacionNoAplica,
)


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

    def actualizar(self, id_paciente: str, cambios: CambiosPaciente) -> None:
        actual = self.registros[id_paciente]
        self.registros[id_paciente] = replace(
            actual,
            nombres=cambios.nombres or actual.nombres,
            apellidos=cambios.apellidos or actual.apellidos,
            fecha_nacimiento=cambios.fecha_nacimiento or actual.fecha_nacimiento,
            contacto=cambios.contacto if cambios.contacto is not None else actual.contacto,
        )

    def agregar_alergias(self, id_paciente: str, alergias: tuple[Alergia, ...]) -> None:
        actual = self.registros[id_paciente]
        self.registros[id_paciente] = replace(
            actual, alergias=(actual.alergias or ()) + tuple(alergias)
        )

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

    def obtener_consulta(self, id_paciente: str, id_consulta: str) -> Consulta | None:
        for c in self.consultas:
            if c.id_paciente == id_paciente and c.id_consulta == id_consulta:
                return c
        return None

    def agregar_a_consulta(
        self, id_paciente: str, id_consulta: str, id_profesional: str, adenda: Adenda
    ) -> Consulta:
        previa = self.obtener_consulta(id_paciente, id_consulta)
        assert previa is not None
        rotulo = adenda.rotular(datetime(2026, 1, 2, tzinfo=UTC), id_profesional)
        nueva = replace(
            previa,
            notas=f"{previa.notas}\n\n{rotulo}" if previa.notas else rotulo,
            diagnosticos=previa.diagnosticos + adenda.diagnosticos,
            tratamientos=previa.tratamientos + adenda.tratamientos,
            recetas=previa.recetas + adenda.recetas,
        )
        self.consultas[self.consultas.index(previa)] = nueva
        return nueva


@dataclass
class ProfesionalesDoble:
    registros: dict[str, ProfesionalLocal] = field(default_factory=dict)

    def obtener(self, id_profesional: str) -> ProfesionalLocal | None:
        return self.registros.get(id_profesional)

    def sincronizar(self, perfil: ProfesionalLocal) -> None:
        self.registros[perfil.id_profesional] = perfil


@dataclass
class CitasDoble:
    registros: dict[str, Cita] = field(default_factory=dict)

    def obtener(self, id_cita: str) -> Cita | None:
        return self.registros.get(id_cita)

    def agendar(self, datos: NuevaCita, nombre_paciente: str, creada_por: str) -> Cita:
        for cita in self.registros.values():
            if (
                cita.estado in ESTADOS_OCUPAN_HORARIO
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
        self.crecimiento = CrecimientoNoAplica("Doble")
        self.vacunacion = VacunacionNoAplica("Doble")
        self.laboratorio = LaboratorioNoAplica("Doble")
        self.hospital = HospitalNoAplica("Doble")
        self.cobros = CobrosNoAplica("Doble")
        self.tutores = TutoresNoAplica("Doble")
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


class CifradorDoble:
    """Hash reversible SOLO para pruebas."""

    def cifrar(self, contrasena: str) -> str:
        return "hash:" + contrasena

    def verificar(self, contrasena: str, cifrada: str) -> bool:
        return cifrada == "hash:" + contrasena


@dataclass
class DirectorioAdministrableDoble:
    """Identidad central en memoria (cuentas + contrasenas + bitacora)."""

    fichas: dict[str, FichaProfesional] = field(default_factory=dict)
    contrasenas: dict[str, str] = field(default_factory=dict)
    bitacora: list[tuple[str, str, str]] = field(default_factory=list)

    def crear(self, institucion, datos, permisos, contrasena_cifrada, id_actor):
        if any(f.correo == datos.correo for f in self.fichas.values()):
            raise ConflictoEstado("Ya existe una cuenta con ese correo.")
        identificador = f"00000000-0000-4000-8000-{len(self.fichas) + 1:012d}"
        ficha = FichaProfesional(
            identificador,
            datos.correo,
            datos.nombres,
            datos.apellidos,
            datos.rol,
            institucion,
            EstadoCuenta.ACTIVA,
            permisos,
            datos.id_departamento,
            debe_cambiar_contrasena=True,
        )
        self.fichas[identificador] = ficha
        self.contrasenas[identificador] = contrasena_cifrada
        self.bitacora.append((id_actor, identificador, "alta"))
        return ficha

    def listar(self, institucion, rol=None, id_departamento=None, estado=None, limite=200):
        return [
            f
            for f in self.fichas.values()
            if f.institucion == institucion
            and (rol is None or f.rol == rol)
            and (id_departamento is None or f.id_departamento == id_departamento)
            and (estado is None or f.estado == estado)
        ][:limite]

    def obtener(self, institucion, id_profesional):
        ficha = self.fichas.get(id_profesional)
        return ficha if ficha and ficha.institucion == institucion else None

    def actualizar(self, institucion, id_profesional, cambios, permisos, id_actor):
        ficha = self.obtener(institucion, id_profesional)
        nuevos = {}
        for campo in ("nombres", "apellidos", "estado"):
            if getattr(cambios, campo) is not None:
                nuevos[campo] = getattr(cambios, campo)
        if cambios.quitar_departamento:
            nuevos["id_departamento"] = None
        elif cambios.id_departamento is not None:
            nuevos["id_departamento"] = cambios.id_departamento
        if permisos is not None:
            nuevos["permisos"] = permisos
        self.fichas[id_profesional] = replace(ficha, **nuevos)
        self.bitacora.append((id_actor, id_profesional, "cambio"))
        return self.fichas[id_profesional]

    def establecer_contrasena(
        self, id_profesional, contrasena_cifrada, debe_cambiar, id_actor, accion
    ):
        self.contrasenas[id_profesional] = contrasena_cifrada
        if id_profesional in self.fichas:
            self.fichas[id_profesional] = replace(
                self.fichas[id_profesional], debe_cambiar_contrasena=debe_cambiar
            )
        self.bitacora.append((id_actor, id_profesional, accion))

    def listar_para_agenda(self, institucion):
        return [
            ProfesionalAgenda(f.id_profesional, f.nombres, f.apellidos, f.rol, f.id_departamento)
            for f in self.fichas.values()
            if f.institucion == institucion
            and f.estado != EstadoCuenta.INACTIVA
            and f.rol not in ("secretaria", "administrador")
        ]
