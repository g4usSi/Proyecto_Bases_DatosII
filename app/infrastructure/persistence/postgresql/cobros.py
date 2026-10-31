"""Hospital General (PostgreSQL): cobros, cargos con tarifa congelada y pagos.

Las reglas de dinero estan en la base (010_integridad_hospital.sql): un pago bloquea su
cobro y no puede exceder el saldo; los cargos solo cambian con el cobro Abierto; Pagado y
Anulado son finales. Aqui se traducen a errores del dominio.
"""

from datetime import datetime
from decimal import Decimal

import psycopg

from app.domain.cobros import (
    Cargo,
    Cobro,
    EstadoCobro,
    MetodoPago,
    NuevoCargo,
    NuevoPago,
    Pago,
    Servicio,
)
from app.domain.errores import ConflictoEstado, DatosInvalidos, RegistroNoEncontrado
from app.infrastructure.persistence.comun import con_utc, entero_positivo, utc_ingenuo

ESTADO_COBRO_BD = {
    EstadoCobro.ABIERTO: "Abierto",
    EstadoCobro.CERRADO: "Cerrado",
    EstadoCobro.PAGADO: "Pagado",
    EstadoCobro.ANULADO: "Anulado",
}
ESTADO_COBRO_DOMINIO = {v: k for k, v in ESTADO_COBRO_BD.items()}
METODO_BD = {
    MetodoPago.EFECTIVO: "Efectivo",
    MetodoPago.TARJETA: "Tarjeta",
    MetodoPago.TRANSFERENCIA: "Transferencia",
    MetodoPago.CHEQUE: "Cheque",
}
METODO_DOMINIO = {v: k for k, v in METODO_BD.items()}

_COBROS = """
SELECT c.id_cobro, a.id_paciente, p.nombres || ' ' || p.apellidos, c.id_atencion, c.estado,
       c.fecha_apertura, c.fecha_cierre, c.descripcion,
       COALESCE((SELECT sum(d.monto) FROM detalle_cobro d WHERE d.id_cobro = c.id_cobro), 0),
       COALESCE((SELECT sum(g.monto) FROM pago g
                 WHERE g.id_cobro = c.id_cobro AND g.estado = 'Confirmado'), 0)
FROM cobro c
JOIN atencion a ON a.id_atencion = c.id_atencion
JOIN paciente p ON p.id_paciente = a.id_paciente
"""


def _mensaje(error: psycopg.Error) -> str:
    return str(error.diag.message_primary or "La base rechazo la operacion.")


class RepositorioCobrosPostgreSQL:
    def __init__(self, conexion: psycopg.Connection) -> None:
        self.conexion = conexion

    def listar_servicios(self) -> list[Servicio]:
        return [
            Servicio(*fila)
            for fila in self.conexion.execute(
                "SELECT s.id_servicio, s.nombre, s.tipo, s.unidad_cobro, t.monto_vigente "
                "FROM servicio s LEFT JOIN tarifa t ON t.id_servicio = s.id_servicio "
                "AND t.activa AND t.id_personal IS NULL "
                "WHERE s.activo ORDER BY s.nombre, s.id_servicio"
            )
        ]

    # ------------------------------------------------------------------ lectura

    def _cargar(self, filas: list[tuple]) -> list[Cobro]:
        if not filas:
            return []
        ids = [f[0] for f in filas]
        cargos: dict[int, list[Cargo]] = {i: [] for i in ids}
        for fila in self.conexion.execute(
            "SELECT d.id_cobro, d.id_detalle_cobro, COALESCE(d.descripcion_aplicada, s.nombre), "
            "d.cantidad, d.precio_unitario_aplicado, d.monto, d.fecha_hora_servicio, s.id_servicio "
            "FROM detalle_cobro d JOIN tarifa t ON t.id_tarifa = d.id_tarifa "
            "JOIN servicio s ON s.id_servicio = t.id_servicio "
            "WHERE d.id_cobro = ANY(%s) ORDER BY d.id_detalle_cobro",
            (ids,),
        ):
            cargos[fila[0]].append(
                Cargo(
                    str(fila[1]),
                    fila[2],
                    Decimal(fila[3]),
                    fila[4],
                    fila[5],
                    con_utc(fila[6]),
                    fila[7],
                )
            )
        pagos: dict[int, list[Pago]] = {i: [] for i in ids}
        for fila in self.conexion.execute(
            "SELECT g.id_cobro, g.id_pago, m.nombre, g.monto, g.fecha_hora, g.estado, g.referencia "
            "FROM pago g JOIN metodo_pago m ON m.id_metodo_pago = g.id_metodo_pago "
            "WHERE g.id_cobro = ANY(%s) ORDER BY g.fecha_hora, g.id_pago",
            (ids,),
        ):
            pagos[fila[0]].append(
                Pago(
                    str(fila[1]),
                    METODO_DOMINIO[fila[2]],
                    fila[3],
                    con_utc(fila[4]),
                    fila[5] == "Anulado",
                    fila[6],
                )
            )
        return [
            Cobro(
                id_cobro=str(f[0]),
                id_paciente=str(f[1]),
                nombre_paciente=f[2],
                id_atencion=str(f[3]),
                estado=ESTADO_COBRO_DOMINIO[f[4]],
                abierto_en=con_utc(f[5]),
                cerrado_en=con_utc(f[6]) if f[6] else None,
                descripcion=f[7],
                total=f[8],
                pagado=f[9],
                cargos=tuple(cargos[f[0]]),
                pagos=tuple(pagos[f[0]]),
            )
            for f in filas
        ]

    def obtener(self, id_paciente: str, id_cobro: str) -> Cobro | None:
        paciente, cobro = entero_positivo(id_paciente), entero_positivo(id_cobro)
        if paciente is None or cobro is None:
            return None
        filas = self.conexion.execute(
            _COBROS + " WHERE c.id_cobro = %s AND a.id_paciente = %s", (cobro, paciente)
        ).fetchall()
        cargados = self._cargar(filas)
        return cargados[0] if cargados else None

    def listar(
        self,
        id_paciente: str | None = None,
        estados: frozenset[EstadoCobro] | None = None,
        limite: int = 100,
    ) -> list[Cobro]:
        filtros, parametros = [], []
        if id_paciente is not None:
            numero = entero_positivo(id_paciente)
            if numero is None:
                return []
            filtros.append("a.id_paciente = %s")
            parametros.append(numero)
        if estados:
            filtros.append("c.estado = ANY(%s)")
            parametros.append([ESTADO_COBRO_BD[e] for e in estados])
        donde = (" WHERE " + " AND ".join(filtros)) if filtros else ""
        filas = self.conexion.execute(
            _COBROS + donde + " ORDER BY c.fecha_apertura DESC, c.id_cobro DESC LIMIT %s",
            (*parametros, limite),
        ).fetchall()
        return self._cargar(filas)

    def _releer(self, id_paciente: str, id_cobro: str) -> Cobro:
        cobro = self.obtener(id_paciente, id_cobro)
        assert cobro is not None
        return cobro

    def _bloquear(self, id_paciente: str, id_cobro: str) -> tuple[int, str, int]:
        """Bloquea el cobro (FOR UPDATE): sus cargos y pagos se procesan de uno en uno."""
        paciente, cobro = entero_positivo(id_paciente), entero_positivo(id_cobro)
        fila = None
        if paciente is not None and cobro is not None:
            fila = self.conexion.execute(
                "SELECT c.id_cobro, c.estado, a.id_personal FROM cobro c "
                "JOIN atencion a ON a.id_atencion = c.id_atencion "
                "WHERE c.id_cobro = %s AND a.id_paciente = %s FOR UPDATE OF c",
                (cobro, paciente),
            ).fetchone()
        if fila is None:
            raise RegistroNoEncontrado("El cobro no existe para ese paciente.")
        return fila

    # ------------------------------------------------------------------ escritura

    def abrir(
        self,
        id_paciente: str,
        id_atencion: str,
        descripcion: str | None,
        ahora: datetime,
        id_tutor: str | None = None,
    ) -> Cobro:
        if id_tutor is not None:
            raise DatosInvalidos("El Hospital General no factura a nombre de un tutor.")
        paciente, atencion = entero_positivo(id_paciente), entero_positivo(id_atencion)
        fila = None
        if paciente is not None and atencion is not None:
            # Bloquea la atencion: dos solicitudes no abren dos cobros vigentes a la vez.
            fila = self.conexion.execute(
                "SELECT id_atencion FROM atencion WHERE id_atencion = %s AND id_paciente = %s "
                "FOR UPDATE",
                (atencion, paciente),
            ).fetchone()
        if fila is None:
            raise RegistroNoEncontrado("La atencion no existe en el historial del paciente.")
        vigente = self.conexion.execute(
            "SELECT id_cobro FROM cobro WHERE id_atencion = %s AND estado <> 'Anulado'",
            (atencion,),
        ).fetchone()
        if vigente is not None:
            raise ConflictoEstado(f"Esa atencion ya tiene el cobro {vigente[0]}.")
        id_cobro = self.conexion.execute(
            "INSERT INTO cobro (id_atencion, fecha_apertura, descripcion) VALUES (%s, %s, %s) "
            "RETURNING id_cobro",
            (atencion, utc_ingenuo(ahora), descripcion),
        ).fetchone()[0]
        return self._releer(id_paciente, str(id_cobro))

    def agregar_cargo(
        self, id_paciente: str, id_cobro: str, cargo: NuevoCargo, ahora: datetime
    ) -> Cobro:
        if cargo.id_servicio is None:
            raise DatosInvalidos("En el Hospital General cada cargo es un servicio (id_servicio).")
        if cargo.precio_unitario is not None:
            raise DatosInvalidos("El precio sale de la tarifa vigente del servicio; no se envia.")
        if cargo.cantidad != cargo.cantidad.to_integral_value():
            raise DatosInvalidos("La cantidad debe ser un numero entero.")
        numero, estado, id_personal = self._bloquear(id_paciente, id_cobro)
        if estado != "Abierto":
            raise ConflictoEstado(f"El cobro esta {estado.lower()} y no admite cargos.")
        # Tarifa propia del profesional de la atencion; si no tiene, la general.
        tarifa = self.conexion.execute(
            "SELECT t.id_tarifa, t.monto_vigente FROM tarifa t "
            "JOIN servicio s ON s.id_servicio = t.id_servicio "
            "WHERE t.id_servicio = %s AND t.activa AND s.activo "
            "AND (t.id_personal = %s OR t.id_personal IS NULL) "
            "ORDER BY (t.id_personal IS NULL) LIMIT 1",
            (cargo.id_servicio, id_personal),
        ).fetchone()
        if tarifa is None:
            raise DatosInvalidos("El servicio no existe o no tiene una tarifa vigente.")
        try:
            self.conexion.execute(
                "INSERT INTO detalle_cobro (id_cobro, id_tarifa, fecha_hora_servicio, "
                "descripcion_aplicada, cantidad, precio_unitario_aplicado) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    numero,
                    tarifa[0],
                    utc_ingenuo(ahora),
                    cargo.concepto,
                    int(cargo.cantidad),
                    tarifa[1],
                ),
            )
        except psycopg.errors.CheckViolation as error:
            raise ConflictoEstado(_mensaje(error)) from error
        return self._releer(id_paciente, id_cobro)

    def registrar_pago(
        self, id_paciente: str, id_cobro: str, pago: NuevoPago, ahora: datetime
    ) -> Cobro:
        numero, _, _ = self._bloquear(id_paciente, id_cobro)
        metodo = self.conexion.execute(
            "SELECT id_metodo_pago FROM metodo_pago WHERE nombre = %s", (METODO_BD[pago.metodo],)
        ).fetchone()
        if metodo is None:
            raise DatosInvalidos("Metodo de pago no disponible.")
        try:
            self.conexion.execute(
                "INSERT INTO pago (id_cobro, id_metodo_pago, monto, fecha_hora, referencia) "
                "VALUES (%s, %s, %s, %s, %s)",
                (numero, metodo[0], pago.monto, utc_ingenuo(ahora), pago.referencia),
            )
        except psycopg.errors.CheckViolation as error:
            raise ConflictoEstado(_mensaje(error)) from error
        cobro = self._releer(id_paciente, id_cobro)
        if (
            cobro.total > 0
            and cobro.saldo == 0
            and cobro.estado
            in (
                EstadoCobro.ABIERTO,
                EstadoCobro.CERRADO,
            )
        ):
            # Saldado: pasa a Pagado (final). El trigger exige que realmente este saldado.
            self.conexion.execute(
                "UPDATE cobro SET estado = 'Pagado', fecha_cierre = COALESCE(fecha_cierre, %s) "
                "WHERE id_cobro = %s",
                (utc_ingenuo(ahora), numero),
            )
            cobro = self._releer(id_paciente, id_cobro)
        return cobro

    def anular_pago(self, id_paciente: str, id_cobro: str, id_pago: str) -> Cobro:
        numero, estado, _ = self._bloquear(id_paciente, id_cobro)
        if estado in ("Pagado", "Anulado"):
            raise ConflictoEstado(f"El cobro esta {estado.lower()}: sus pagos ya no cambian.")
        pago = entero_positivo(id_pago)
        fila = None
        if pago is not None:
            fila = self.conexion.execute(
                "SELECT estado FROM pago WHERE id_pago = %s AND id_cobro = %s", (pago, numero)
            ).fetchone()
        if fila is None:
            raise RegistroNoEncontrado("El pago no existe en ese cobro.")
        if fila[0] == "Anulado":
            raise ConflictoEstado("El pago ya estaba anulado.")
        self.conexion.execute("UPDATE pago SET estado = 'Anulado' WHERE id_pago = %s", (pago,))
        return self._releer(id_paciente, id_cobro)

    def _cambiar_estado(
        self, id_paciente: str, id_cobro: str, nuevo: str, desde: tuple[str, ...], ahora: datetime
    ) -> Cobro:
        numero, estado, _ = self._bloquear(id_paciente, id_cobro)
        if estado not in desde:
            raise ConflictoEstado(f"El cobro esta {estado.lower()} y no puede pasar a {nuevo}.")
        try:
            self.conexion.execute(
                "UPDATE cobro SET estado = %s, fecha_cierre = COALESCE(fecha_cierre, %s) "
                "WHERE id_cobro = %s",
                (nuevo, utc_ingenuo(ahora), numero),
            )
        except psycopg.errors.CheckViolation as error:
            raise ConflictoEstado(_mensaje(error)) from error
        return self._releer(id_paciente, id_cobro)

    def cerrar(self, id_paciente: str, id_cobro: str, ahora: datetime) -> Cobro:
        return self._cambiar_estado(id_paciente, id_cobro, "Cerrado", ("Abierto",), ahora)

    def anular(self, id_paciente: str, id_cobro: str, ahora: datetime) -> Cobro:
        return self._cambiar_estado(id_paciente, id_cobro, "Anulado", ("Abierto", "Cerrado"), ahora)
