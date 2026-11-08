"""Carga administrativa de catalogos (de una vez, con la cuenta administrativa).

    python -m scripts.cargar_catalogos vacunas  database/ejemplos/catalogo_vacunas_demo.json
    python -m scripts.cargar_catalogos laboratorio database/ejemplos/catalogo_laboratorio_demo.json
    python -m scripts.cargar_catalogos laboratorio archivo.json --desactivar-anteriores

Usa las cuentas administrativas de .env (MYSQL_ROOT_PASSWORD / MONGO_ROOT_PASSWORD).
Los archivos de database/ejemplos son DEMOSTRACIONES: el hospital y el laboratorio deben
validar sus esquemas, edades y rangos de referencia antes de usarlos con pacientes.

Reglas:
- Vacunas: el tipo (nombre, edad recomendada, dosis) se crea o actualiza. No hay lotes ni
  existencias: el equipo decidio no controlar stock (migracion MySQL 010). Despues de la
  carga, el administrador del Centro Pediatrico puede agregar vacunas y corregir su
  descripcion desde la aplicacion (POST/PUT /vacunas, migracion MySQL 018).
- Laboratorio: una (codigo, version) publicada es inmutable. Si cambia un rango o un
  parametro, publica una version nueva (y usa --desactivar-anteriores).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pymysql

from app.core.config import Settings
from scripts.sincronizar_profesionales import _conectar_mongo_admin, _conectar_mysql_admin


class CatalogoInvalido(Exception):
    """El archivo no cumple el formato esperado o contradice lo ya publicado."""


def _texto(valor: Any, campo: str, obligatorio: bool = True) -> str | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        if obligatorio:
            raise CatalogoInvalido(f"Falta '{campo}'.")
        return None
    if not isinstance(valor, str):
        raise CatalogoInvalido(f"'{campo}' debe ser texto.")
    return valor.strip()


def _entero(valor: Any, campo: str, minimo: int = 0) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo:
        raise CatalogoInvalido(f"'{campo}' debe ser un entero >= {minimo}.")
    return valor


def cargar_vacunas(conexion: pymysql.Connection, datos: dict[str, Any]) -> dict[str, int]:
    """Crea o actualiza los tipos de vacuna. No maneja lotes ni existencias."""
    resumen = {"tipos_nuevos": 0, "tipos_actualizados": 0}
    vacunas = datos.get("vacunas")
    if not isinstance(vacunas, list) or not vacunas:
        raise CatalogoInvalido("El archivo debe traer una lista 'vacunas'.")
    with conexion.cursor() as cursor:
        for vacuna in vacunas:
            nombre = _texto(vacuna.get("nombre"), "nombre")
            edad = vacuna.get("edad_recomendada_meses")
            if edad is not None:
                edad = _entero(edad, "edad_recomendada_meses")
            campos = (
                _texto(vacuna.get("enfermedades_que_previene"), "enfermedades", False),
                edad,
                _texto(vacuna.get("dosis_sugerida"), "dosis_sugerida", False),
            )
            cursor.execute(
                "SELECT id_nombre_vacuna FROM nombre_vacuna WHERE nombre = %s", (nombre,)
            )
            fila = cursor.fetchone()
            if fila is None:
                cursor.execute(
                    "INSERT INTO nombre_vacuna (nombre, enfermedades_que_previene, "
                    "edad_recomendada_meses, dosis_sugerida) VALUES (%s, %s, %s, %s)",
                    (nombre, *campos),
                )
                id_tipo = cursor.lastrowid
                resumen["tipos_nuevos"] += 1
            else:
                id_tipo = fila[0]
                cursor.execute(
                    "UPDATE nombre_vacuna SET enfermedades_que_previene = %s, "
                    "edad_recomendada_meses = %s, dosis_sugerida = %s WHERE id_nombre_vacuna = %s",
                    (*campos, id_tipo),
                )
                resumen["tipos_actualizados"] += 1
    conexion.commit()
    return resumen


def _validar_prueba(prueba: dict[str, Any]) -> dict[str, Any]:
    codigo = _texto(prueba.get("codigo"), "codigo")
    parametros = prueba.get("parametros")
    if not isinstance(parametros, list) or not parametros:
        raise CatalogoInvalido(f"La prueba {codigo} necesita al menos un parametro.")
    vistos: set[str] = set()
    limpios = []
    for p in parametros:
        pc = _texto(p.get("codigo"), "codigo del parametro")
        if pc in vistos:
            raise CatalogoInvalido(f"Parametro repetido en {codigo}: {pc}.")
        vistos.add(pc)
        if p.get("tipo_valor") not in ("numerico", "texto", "booleano"):
            raise CatalogoInvalido(f"Tipo de valor invalido en {codigo}/{pc}.")
        limpio = {k: v for k, v in p.items() if v is not None}
        limpio["codigo"], limpio["nombre"] = pc, _texto(p.get("nombre"), "nombre del parametro")
        limpios.append(limpio)
    documento = {
        "codigo": codigo,
        "nombre": _texto(prueba.get("nombre"), "nombre"),
        "version": _entero(prueba.get("version", 1), "version", minimo=1),
        "activo": bool(prueba.get("activo", True)),
        "parametros": limpios,
    }
    for opcional in ("tipo_muestra", "indicaciones"):
        valor = _texto(prueba.get(opcional), opcional, False)
        if valor:
            documento[opcional] = valor
    return documento


def cargar_pruebas(
    coleccion, datos: dict[str, Any], desactivar_anteriores: bool = False
) -> dict[str, int]:
    """Publica pruebas nuevas. Una (codigo, version) ya publicada solo se acepta si es identica."""
    resumen = {"publicadas": 0, "sin_cambios": 0, "desactivadas": 0}
    pruebas = datos.get("pruebas")
    if not isinstance(pruebas, list) or not pruebas:
        raise CatalogoInvalido("El archivo debe traer una lista 'pruebas'.")
    documentos = [_validar_prueba(p) for p in pruebas]  # valida todo antes de escribir
    for documento in documentos:
        existente = coleccion.find_one(
            {"codigo": documento["codigo"], "version": documento["version"]}, {"_id": 0}
        )
        if existente is None:
            coleccion.insert_one(documento)
            resumen["publicadas"] += 1
        elif {k: v for k, v in existente.items() if k != "activo"} == {
            k: v for k, v in documento.items() if k != "activo"
        }:
            resumen["sin_cambios"] += 1
        else:
            raise CatalogoInvalido(
                f"{documento['codigo']} v{documento['version']} ya esta publicada con otro "
                "contenido; publica una version nueva."
            )
        if desactivar_anteriores:
            resultado = coleccion.update_many(
                {
                    "codigo": documento["codigo"],
                    "version": {"$lt": documento["version"]},
                    "activo": True,
                },
                {"$set": {"activo": False}},
            )
            resumen["desactivadas"] += resultado.modified_count
    return resumen


def _leer(ruta: str) -> dict[str, Any]:
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CatalogoInvalido(f"No se pudo leer {ruta}: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="catalogo", required=True)
    sub.add_parser("vacunas").add_argument("archivo")
    lab = sub.add_parser("laboratorio")
    lab.add_argument("archivo")
    lab.add_argument("--desactivar-anteriores", action="store_true")
    args = parser.parse_args()
    try:
        datos = _leer(args.archivo)
        if args.catalogo == "vacunas":
            conexion = _conectar_mysql_admin()
            try:
                print("Vacunas:", cargar_vacunas(conexion, datos))
            finally:
                conexion.close()
        else:
            cliente, _ = _conectar_mongo_admin()
            try:
                coleccion = cliente[Settings().mongodb_database].catalogo_pruebas
                print("Laboratorio:", cargar_pruebas(coleccion, datos, args.desactivar_anteriores))
            finally:
                cliente.close()
    except (CatalogoInvalido, RuntimeError) as error:
        print(f"Error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
