from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from uuid import uuid4

import pymysql
import pytest


def test_alergias_multiples_y_tutores_compartidos(mysql_datos):
    conn, pacientes, _, _ = mysql_datos
    with conn.cursor() as c:
        for _ in range(2):
            c.execute("INSERT INTO alergias_conocidas(nombre) VALUES (%s)", (uuid4().hex,))
            c.execute(
                "INSERT INTO paciente_alergia VALUES (%s,%s,NULL,NULL,NULL,NOW())",
                (pacientes[0], c.lastrowid),
            )
        c.execute(
            "INSERT INTO tutor(nombre,apellido,correo_electronico) "
            "VALUES ('Prueba','Tutor','compartido@example.invalid')"
        )
        tutor = c.lastrowid
        for paciente, relacion in zip(pacientes, ["Madre", "Tia"], strict=True):
            c.execute(
                "INSERT INTO paciente_tutor(id_paciente,id_tutor,parentesco,es_principal) "
                "VALUES (%s,%s,%s,1)",
                (paciente, tutor, relacion),
            )
        c.execute("SELECT COUNT(*) FROM paciente_alergia WHERE id_paciente=%s", (pacientes[0],))
        assert c.fetchone()[0] == 2
        c.execute("INSERT INTO tutor(nombre,apellido) VALUES ('Segundo','Tutor')")
        with pytest.raises(pymysql.IntegrityError):
            c.execute(
                "INSERT INTO paciente_tutor(id_paciente,id_tutor,parentesco,es_principal) "
                "VALUES (%s,%s,'Padre',1)",
                (pacientes[0], c.lastrowid),
            )


def test_crecimiento_no_se_asigna_a_otro_paciente(mysql_datos):
    conn, pacientes, medico, _ = mysql_datos
    with conn.cursor() as c:
        c.execute(
            "INSERT INTO control_crecimiento(id_paciente_fk,peso_kg) VALUES (%s,15)",
            (pacientes[1],),
        )
        with pytest.raises(pymysql.IntegrityError):
            c.execute(
                "INSERT INTO consulta_medica(id_paciente,id_medico,id_control,motivo_consulta) "
                "VALUES (%s,%s,%s,'Prueba')",
                (pacientes[0], medico, c.lastrowid),
            )
        with pytest.raises(pymysql.OperationalError):
            c.execute(
                "INSERT INTO control_crecimiento(id_paciente_fk,percentil_peso) VALUES (%s,101)",
                (pacientes[0],),
            )


def test_archivo_requiere_motivo_y_conserva_consultas(mysql_datos):
    conn, pacientes, medico, consulta = mysql_datos
    with conn.cursor() as c:
        with pytest.raises(pymysql.OperationalError):
            c.execute("UPDATE paciente SET archivado=1 WHERE id_paciente=%s", (pacientes[0],))
        c.execute(
            "UPDATE paciente SET archivado=1,fecha_baja=NOW(),motivo_baja='Prueba' "
            "WHERE id_paciente=%s",
            (pacientes[0],),
        )
        with pytest.raises(pymysql.OperationalError):
            c.execute(
                "INSERT INTO consulta_medica(id_paciente,id_medico,motivo_consulta) "
                "VALUES (%s,%s,'No permitido')",
                (pacientes[0], medico),
            )
        c.execute("SELECT id_consulta FROM consulta_medica WHERE id_consulta=%s", (consulta,))
        assert c.fetchone()[0] == consulta


def test_vacuna_stock_atomicidad_y_lote(mysql_datos):
    conn, pacientes, medico, _ = mysql_datos
    with conn.cursor() as c:
        c.execute("INSERT INTO nombre_vacuna(nombre) VALUES (%s)", (uuid4().hex,))
        tipo = c.lastrowid
        c.execute(
            "INSERT INTO catalogo_vacunas(nombre_vacuna_fk,lote_vacuna,fecha_vencimiento,cantidad) "
            "VALUES (%s,%s,%s,1)",
            (tipo, uuid4().hex, date.today() + timedelta(days=30)),
        )
        lote = c.lastrowid
        sql = (
            "INSERT INTO esquema_vacunacion(id_paciente_fk,id_nombre_vacuna_fk,id_vacuna_fk,"
            "fecha_aplicacion,estado_aplicacion,id_medico_aplicador) "
            "VALUES (%s,%s,%s,NOW(),'Aplicada',%s)"
        )
        c.execute(sql, (pacientes[0], tipo, lote, medico))
        aplicacion = c.lastrowid
        with pytest.raises(pymysql.OperationalError):
            c.execute(sql, (pacientes[1], tipo, lote, medico))
        c.execute("SELECT cantidad FROM catalogo_vacunas WHERE id_vacuna=%s", (lote,))
        assert c.fetchone()[0] == 0
        with pytest.raises(pymysql.OperationalError):
            c.execute("DELETE FROM esquema_vacunacion WHERE id_esquema=%s", (aplicacion,))
        c.execute("SELECT COUNT(*) FROM esquema_vacunacion WHERE id_vacuna_fk=%s", (lote,))
        assert c.fetchone()[0] == 1


def test_saldos_insert_update_delete_y_cargos(mysql_datos):
    conn, _, _, consulta = mysql_datos
    with conn.cursor() as c:
        c.execute("INSERT INTO facturacion(id_consulta_fk) VALUES (%s)", (consulta,))
        factura = c.lastrowid
        c.execute(
            "INSERT INTO detalle_facturacion(id_facturacion,concepto,cantidad,precio_unitario) "
            "VALUES (%s,'Prueba',1,100)",
            (factura,),
        )
        detalle = c.lastrowid
        c.execute(
            "INSERT INTO pago(id_facturacion,id_tipo_pago,monto) VALUES (%s,1,80)", (factura,)
        )
        pago = c.lastrowid
        with pytest.raises(pymysql.OperationalError):
            c.execute("UPDATE pago SET monto=101 WHERE id_pago=%s", (pago,))
        with pytest.raises(pymysql.OperationalError):
            c.execute("DELETE FROM detalle_facturacion WHERE id_detalle=%s", (detalle,))
        c.execute("UPDATE pago SET monto=60 WHERE id_pago=%s", (pago,))
        c.execute(
            "UPDATE detalle_facturacion SET precio_unitario=70 WHERE id_detalle=%s", (detalle,)
        )
        c.execute(
            "SELECT total_facturado,total_pagado FROM facturacion WHERE id_facturacion=%s",
            (factura,),
        )
        assert tuple(map(int, c.fetchone())) == (70, 60)
        c.execute("DELETE FROM pago WHERE id_pago=%s", (pago,))
        c.execute("SELECT total_pagado FROM facturacion WHERE id_facturacion=%s", (factura,))
        assert c.fetchone()[0] == 0


def test_dos_pagos_simultaneos_no_superan_total(mysql_datos, mysql_pruebas):
    conn, _, _, consulta = mysql_datos
    with conn.cursor() as c:
        c.execute("INSERT INTO facturacion(id_consulta_fk) VALUES (%s)", (consulta,))
        factura = c.lastrowid
        c.execute(
            "INSERT INTO detalle_facturacion(id_facturacion,concepto,cantidad,precio_unitario) "
            "VALUES (%s,'Prueba concurrente',1,100)",
            (factura,),
        )
    conn.commit()  # Datos sinteticos SOLO en la BD temporal de la prueba.
    barrera = Barrier(2)

    def pagar():
        otra = pymysql.connect(**mysql_pruebas)
        try:
            barrera.wait(timeout=10)
            with otra.cursor() as c:
                c.execute(
                    "INSERT INTO pago(id_facturacion,id_tipo_pago,monto) VALUES (%s,1,80)",
                    (factura,),
                )
            otra.commit()
            return True
        except pymysql.OperationalError as error:
            otra.rollback()
            assert error.args[0] == 3819  # CHECK, no otro fallo accidental.
            return False
        finally:
            otra.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(lambda _: pagar(), range(2)))
    assert sorted(resultados) == [False, True]
    with conn.cursor() as c:
        c.execute("SELECT total_pagado FROM facturacion WHERE id_facturacion=%s", (factura,))
        assert c.fetchone()[0] == 80
