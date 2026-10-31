"""Centro Pediatrico (MySQL): facturas por consulta a nombre de un tutor, cargos y pagos.

Usa el modulo de facturacion de 001/002: los totales los mantienen triggers que bloquean la
factura, y el CHECK total_pagado <= total_facturado impide pagar de mas aunque dos pagos
lleguen a la vez. 015 agrega la anulacion (solo sin pagos; despues no admite cargos ni
pagos) y el tutor facturado. No hay cierre ni anulacion de pagos: responden 501.
"""

from datetime import datetime

import pymysql

from app.domain.cobros import (
    Cargo,
    Cobro,
    EstadoCobro,
    MetodoPago,
    NuevoCargo,
    NuevoPago,
    Pago,
    Servicio,
    TitularCobro,
)
from app.domain.errores import ConflictoEstado, DatosInvalidos, RegistroNoEncontrado
from app.infrastructure.persistence.comun import con_utc, entero_positivo, utc_ingenuo
from app.infrastructure.persistence.pendiente import pendiente

MOTOR = "MySQL"
ER_CHECK_VIOLADO = 3819
ER_SENAL = 1644  # SIGNAL de un trigger
METODO_BD = {
    MetodoPago.EFECTIVO: "Efectivo",
    MetodoPago.TARJETA: "Tarjeta",
    MetodoPago.TRANSFERENCIA: "Transferencia",
    MetodoPago.CHEQUE: "Cheque",
}
METODO_DOMINIO = {v: k for k, v in METODO_BD.items()}

_FACTURAS = """
SELECT f.id_facturacion, c.id_paciente, CONCAT(p.nombre, ' ', p.apellido), f.id_consulta_fk,
       f.fecha_emision, f.descripcion, f.total_facturado, f.total_pagado, f.anulada_en,
       f.id_tutor_fk, CONCAT(t.nombre, ' ', t.apellido)
FROM facturacion f
JOIN consulta_medica c ON c.id_consulta = f.id_consulta_fk
JOIN paciente p ON p.id_paciente = c.id_paciente
LEFT JOIN tutor t ON t.id_tutor = f.id_tutor_fk
"""
_ANULADA = "(f.anulada_en IS NOT NULL)"
_PAGADA = f"(NOT {_ANULADA} AND f.total_facturado > 0 AND f.total_pagado = f.total_facturado)"
_POR_COBRAR = f"(NOT {_ANULADA} AND NOT {_PAGADA})"


def _estado(fila: tuple) -> EstadoCobro:
    if fila[8] is not None:
        return EstadoCobro.ANULADO
    if fila[6] > 0 and fila[7] == fila[6]:
        return EstadoCobro.PAGADO
    return EstadoCobro.ABIERTO


class RepositorioCobrosMySQL:
    def __init__(self, conexion: pymysql.Connection) -> None:
        self.conexion = conexion

    def _filas(self, sql: str, parametros: tuple = ()) -> tuple[tuple, ...]:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.fetchall()

    def _ejecutar(self, sql: str, parametros: tuple = ()) -> int:
        with self.conexion.cursor() as cursor:
            cursor.execute(sql, parametros)
            return cursor.lastrowid

    def listar_servicios(self) -> list[Servicio]:
        pendiente(
            MOTOR, "catalogo de servicios (en el Centro Pediatrico cada cargo lleva su concepto)"
        )

    # ------------------------------------------------------------------ lectura

    def _cargar(self, filas: tuple[tuple, ...]) -> list[Cobro]:
        if not filas:
            return []
        ids = tuple(f[0] for f in filas)
        marcas = ", ".join(["%s"] * len(ids))
        emision = {f[0]: f[4] for f in filas}
        cargos: dict[int, list[Cargo]] = {i: [] for i in ids}
        for fila in self._filas(
            "SELECT id_facturacion, id_detalle, concepto, cantidad, precio_unitario, monto "
            f"FROM detalle_facturacion WHERE id_facturacion IN ({marcas}) ORDER BY id_detalle",
            ids,
        ):
            # El modelo no guarda la hora de cada cargo: se usa la emision de la factura.
            cargos[fila[0]].append(
                Cargo(str(fila[1]), fila[2], fila[3], fila[4], fila[5], con_utc(emision[fila[0]]))
            )
        pagos: dict[int, list[Pago]] = {i: [] for i in ids}
        for fila in self._filas(
            "SELECT g.id_facturacion, g.id_pago, t.nombre, g.monto, g.fecha_pago, g.referencia "
            "FROM pago g JOIN tipo_de_pago t ON t.id_tipo_pago = g.id_tipo_pago "
            f"WHERE g.id_facturacion IN ({marcas}) ORDER BY g.fecha_pago, g.id_pago",
            ids,
        ):
            pagos[fila[0]].append(
                Pago(
                    str(fila[1]),
                    METODO_DOMINIO.get(fila[2], MetodoPago.EFECTIVO),
                    fila[3],
                    con_utc(fila[4]),
                    False,
                    fila[5],
                )
            )
        return [
            Cobro(
                id_cobro=str(f[0]),
                id_paciente=str(f[1]),
                nombre_paciente=f[2],
                id_atencion=str(f[3]),
                estado=_estado(f),
                abierto_en=con_utc(f[4]),
                cerrado_en=con_utc(f[8]) if f[8] is not None else None,
                descripcion=f[5],
                facturado_a=TitularCobro(str(f[9]), f[10]) if f[9] is not None else None,
                total=f[6],
                pagado=f[7],
                cargos=tuple(cargos[f[0]]),
                pagos=tuple(pagos[f[0]]),
            )
            for f in filas
        ]

    def obtener(self, id_paciente: str, id_cobro: str) -> Cobro | None:
        paciente, factura = entero_positivo(id_paciente), entero_positivo(id_cobro)
        if paciente is None or factura is None:
            return None
        cargados = self._cargar(
            self._filas(
                _FACTURAS + " WHERE f.id_facturacion = %s AND c.id_paciente = %s",
                (factura, paciente),
            )
        )
        return cargados[0] if cargados else None

    def listar(
        self,
        id_paciente: str | None = None,
        estados: frozenset[EstadoCobro] | None = None,
        limite: int = 100,
    ) -> list[Cobro]:
        filtros: list[str] = []
        parametros: list = []
        if id_paciente is not None:
            numero = entero_positivo(id_paciente)
            if numero is None:
                return []
            filtros.append("c.id_paciente = %s")
            parametros.append(numero)
        if estados:
            # Aqui existen abierto (por cobrar: con saldo o sin cargos), pagado y anulado.
            opciones = []
            if EstadoCobro.PAGADO in estados:
                opciones.append(_PAGADA)
            if EstadoCobro.ABIERTO in estados:
                opciones.append(_POR_COBRAR)
            if EstadoCobro.ANULADO in estados:
                opciones.append(_ANULADA)
            if not opciones:
                return []
            filtros.append("(" + " OR ".join(opciones) + ")")
        donde = (" WHERE " + " AND ".join(filtros)) if filtros else ""
        return self._cargar(
            self._filas(
                _FACTURAS
                + donde
                + " ORDER BY f.fecha_emision DESC, f.id_facturacion DESC LIMIT %s",
                (*parametros, limite),
            )
        )

    def _releer(self, id_paciente: str, id_cobro: str) -> Cobro:
        cobro = self.obtener(id_paciente, id_cobro)
        assert cobro is not None
        return cobro

    def _factura(self, id_paciente: str, id_cobro: str) -> int:
        """La factura vigente (no anulada). El trigger lo vuelve a comprobar con bloqueo."""
        cobro = self.obtener(id_paciente, id_cobro)
        if cobro is None:
            raise RegistroNoEncontrado("El cobro no existe para ese paciente.")
        if cobro.estado == EstadoCobro.ANULADO:
            raise ConflictoEstado("La factura esta anulada: no admite cargos ni pagos.")
        return int(cobro.id_cobro)

    def _insertar(self, sql: str, parametros: tuple) -> None:
        try:
            self._ejecutar(sql, parametros)
        except pymysql.MySQLError as error:
            if error.args and error.args[0] == ER_SENAL and "anulada" in str(error.args[1]):
                raise ConflictoEstado(
                    "La factura esta anulada: no admite cargos ni pagos."
                ) from error
            raise

    # ------------------------------------------------------------------ escritura

    def abrir(
        self,
        id_paciente: str,
        id_atencion: str,
        descripcion: str | None,
        ahora: datetime,
        id_tutor: str | None = None,
    ) -> Cobro:
        paciente, consulta = entero_positivo(id_paciente), entero_positivo(id_atencion)
        if paciente is None or consulta is None:
            raise RegistroNoEncontrado("La consulta no existe en el historial del paciente.")
        # Bloquea al paciente: dos solicitudes no facturan dos veces la misma consulta.
        self._filas(
            "SELECT id_paciente FROM paciente WHERE id_paciente = %s FOR UPDATE", (paciente,)
        )
        existe = self._filas(
            "SELECT 1 FROM consulta_medica WHERE id_consulta = %s AND id_paciente = %s",
            (consulta, paciente),
        )
        if not existe:
            raise RegistroNoEncontrado("La consulta no existe en el historial del paciente.")
        # Una anulada no impide emitir otra para la misma consulta.
        vigente = self._filas(
            "SELECT id_facturacion FROM facturacion WHERE id_consulta_fk = %s "
            "AND anulada_en IS NULL",
            (consulta,),
        )
        if vigente:
            raise ConflictoEstado(f"Esa consulta ya tiene la factura {vigente[0][0]}.")
        tutor = self._titular(paciente, id_tutor)
        id_factura = self._ejecutar(
            "INSERT INTO facturacion (id_consulta_fk, fecha_emision, descripcion, id_tutor_fk) "
            "VALUES (%s, %s, %s, %s)",
            (consulta, utc_ingenuo(ahora), descripcion, tutor),
        )
        return self._releer(id_paciente, str(id_factura))

    def _titular(self, paciente: int, id_tutor: str | None) -> int | None:
        """El tutor pedido (debe estar vinculado) o, si no se indica, el principal."""
        if id_tutor is None:
            principal = self._filas(
                "SELECT id_tutor FROM paciente_tutor WHERE id_paciente = %s AND es_principal",
                (paciente,),
            )
            return principal[0][0] if principal else None
        numero = entero_positivo(id_tutor)
        vinculado = (
            self._filas(
                "SELECT 1 FROM paciente_tutor WHERE id_paciente = %s AND id_tutor = %s",
                (paciente, numero),
            )
            if numero is not None
            else ()
        )
        if not vinculado:
            raise DatosInvalidos("Ese tutor no esta vinculado al paciente.")
        return numero

    def agregar_cargo(
        self, id_paciente: str, id_cobro: str, cargo: NuevoCargo, ahora: datetime
    ) -> Cobro:
        if cargo.id_servicio is not None:
            raise DatosInvalidos(
                "El Centro Pediatrico no usa catalogo de servicios: envia concepto y precio."
            )
        if not (cargo.concepto or "").strip() or cargo.precio_unitario is None:
            raise DatosInvalidos("Cada cargo necesita concepto y precio_unitario.")
        factura = self._factura(id_paciente, id_cobro)
        self._insertar(
            "INSERT INTO detalle_facturacion (id_facturacion, concepto, cantidad, precio_unitario) "
            "VALUES (%s, %s, %s, %s)",
            (factura, cargo.concepto, cargo.cantidad, cargo.precio_unitario),
        )
        return self._releer(id_paciente, id_cobro)

    def registrar_pago(
        self, id_paciente: str, id_cobro: str, pago: NuevoPago, ahora: datetime
    ) -> Cobro:
        factura = self._factura(id_paciente, id_cobro)
        tipo = self._filas(
            "SELECT id_tipo_pago FROM tipo_de_pago WHERE nombre = %s", (METODO_BD[pago.metodo],)
        )
        if not tipo:
            raise DatosInvalidos(f"El Centro Pediatrico no acepta pagos con {pago.metodo.value}.")
        try:
            self._insertar(
                "INSERT INTO pago (id_facturacion, id_tipo_pago, monto, fecha_pago, referencia) "
                "VALUES (%s, %s, %s, %s, %s)",
                (factura, tipo[0][0], pago.monto, utc_ingenuo(ahora), pago.referencia),
            )
        except pymysql.MySQLError as error:
            if error.args and error.args[0] == ER_CHECK_VIOLADO:
                raise ConflictoEstado("El pago excede el saldo pendiente de la factura.") from error
            raise
        return self._releer(id_paciente, id_cobro)

    def anular_pago(self, id_paciente: str, id_cobro: str, id_pago: str) -> Cobro:
        pendiente(MOTOR, "anular pagos (la facturacion pediatrica no registra anulaciones)")

    def cerrar(self, id_paciente: str, id_cobro: str, ahora: datetime) -> Cobro:
        pendiente(MOTOR, "cerrar facturas (una factura queda pagada al saldarse)")

    def anular(self, id_paciente: str, id_cobro: str, ahora: datetime) -> Cobro:
        """Solo sin pagos. Bloquea la factura: un pago simultaneo espera y luego ve la
        anulacion (el trigger lo rechaza), o la anulacion ve su pago (CHECK)."""
        cobro = self.obtener(id_paciente, id_cobro)
        if cobro is None:
            raise RegistroNoEncontrado("El cobro no existe para ese paciente.")
        fila = self._filas(
            "SELECT anulada_en, total_pagado FROM facturacion WHERE id_facturacion = %s FOR UPDATE",
            (int(cobro.id_cobro),),
        )[0]
        if fila[0] is not None:
            raise ConflictoEstado("La factura ya estaba anulada.")
        if fila[1] > 0:
            raise ConflictoEstado("La factura tiene pagos: no se puede anular.")
        try:
            self._ejecutar(
                "UPDATE facturacion SET anulada_en = %s WHERE id_facturacion = %s",
                (utc_ingenuo(ahora), int(cobro.id_cobro)),
            )
        except pymysql.MySQLError as error:
            if error.args and error.args[0] == ER_CHECK_VIOLADO:
                raise ConflictoEstado("La factura tiene pagos: no se puede anular.") from error
            raise
        return self._releer(id_paciente, id_cobro)
