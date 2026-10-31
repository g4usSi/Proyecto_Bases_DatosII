"""Cobros con dobles: 501 fuera del hospital y del centro pediatrico, validaciones y permisos."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain.cobros import MetodoPago, NuevoCargo, NuevoPago
from app.domain.errores import DatosInvalidos
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.domain.paciente import Paciente
from app.main import create_app
from tests.doubles import AutenticadorDoble, UnidadTrabajoDoble

H = {"Authorization": "Bearer t"}


def cliente(settings: Settings, permisos=frozenset({"pagos:ver", "pagos:registrar"})):
    usuario = UsuarioAutenticado("u1", Institucion.CLINICA_ODONTOLOGICA, permisos)
    unidad = UnidadTrabajoDoble({"1": Paciente("1", "Ana", "Lopez")})
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"t": usuario}),
        unidades_trabajo={Institucion.CLINICA_ODONTOLOGICA: lambda: unidad},
    )
    return TestClient(create_app(settings, contenedor))


def test_fuera_del_hospital_y_del_centro_pediatrico_responde_501(settings: Settings) -> None:
    with cliente(settings) as client:
        tablero = client.get("/api/v1/cobros", headers=H)
        abrir = client.post("/api/v1/pacientes/1/cobros", json={"id_atencion": "1"}, headers=H)
    assert tablero.status_code == 501 and "Centro Pediatrico" in tablero.text
    assert abrir.status_code == 501


def test_validaciones_de_montos(settings: Settings) -> None:
    with cliente(settings) as client:
        cero = client.post(
            "/api/v1/pacientes/1/cobros/1/pagos",
            json={"metodo": "efectivo", "monto": "0"},
            headers=H,
        )
        metodo = client.post(
            "/api/v1/pacientes/1/cobros/1/pagos",
            json={"metodo": "bitcoin", "monto": "1"},
            headers=H,
        )
        cantidad = client.post(
            "/api/v1/pacientes/1/cobros/1/cargos",
            json={"cantidad": "0", "concepto": "X"},
            headers=H,
        )
        decimales = client.post(
            "/api/v1/pacientes/1/cobros/1/pagos",
            json={"metodo": "efectivo", "monto": "1.001"},
            headers=H,
        )
    assert {cero.status_code, metodo.status_code, cantidad.status_code, decimales.status_code} == {
        422
    }


def test_ver_no_permite_registrar(settings: Settings) -> None:
    with cliente(settings, frozenset({"pagos:ver"})) as client:
        respuesta = client.post("/api/v1/pacientes/1/cobros", json={"id_atencion": "1"}, headers=H)
    assert respuesta.status_code == 403


def test_reglas_de_cargo_y_pago() -> None:
    NuevoCargo(Decimal(1), id_servicio=3).validar()
    NuevoPago(MetodoPago.TARJETA, Decimal("10.50")).validar()
    for invalido in (
        NuevoCargo(Decimal(0), concepto="X"),
        NuevoCargo(Decimal(1)),
        NuevoCargo(Decimal(1), concepto="X", precio_unitario=Decimal("-1")),
        NuevoPago(MetodoPago.EFECTIVO, Decimal("0")),
        NuevoPago(MetodoPago.EFECTIVO, Decimal("0.001")),
    ):
        with pytest.raises(DatosInvalidos):
            invalido.validar()


def test_superusuario_lee_pagos_eligiendo_la_entidad_y_no_registra(settings: Settings) -> None:
    superusuario = UsuarioAutenticado(
        "su", None, frozenset({"plataforma:administrar", "pagos:ver"})
    )
    cajero = UsuarioAutenticado(
        "c1", Institucion.CENTRO_PEDIATRICO, frozenset({"pagos:ver", "pagos:registrar"})
    )
    abiertas: list[Institucion] = []

    def fabrica(institucion):
        def abrir():
            abiertas.append(institucion)
            return UnidadTrabajoDoble({})

        return abrir

    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"su": superusuario, "caja": cajero}),
        unidades_trabajo={i: fabrica(i) for i in Institucion},
    )
    su, caja = {"Authorization": "Bearer su"}, {"Authorization": "Bearer caja"}
    with TestClient(create_app(settings, contenedor)) as client:
        sin_entidad = client.get("/api/v1/cobros", headers=su)
        laboratorio = client.get(
            "/api/v1/cobros", params={"establecimiento": "laboratorio_clinico"}, headers=su
        )
        pediatria = client.get(
            "/api/v1/cobros", params={"establecimiento": "centro_pediatrico"}, headers=su
        )
        registrar = client.post("/api/v1/pacientes/1/cobros", json={"id_atencion": "1"}, headers=su)
        ajena = client.get(
            "/api/v1/cobros", params={"establecimiento": "hospital_general"}, headers=caja
        )
        propia = client.get("/api/v1/cobros", headers=caja)
    assert sin_entidad.status_code == 422 and laboratorio.status_code == 422
    # El doble no implementa cobros (501): lo importante es que abrio el motor pedido.
    assert pediatria.status_code == 501 and registrar.status_code == 403
    assert ajena.status_code == 403 and propia.status_code == 501
    assert abiertas == [Institucion.CENTRO_PEDIATRICO, Institucion.CENTRO_PEDIATRICO]


def test_el_hospital_no_factura_a_nombre_de_un_tutor(settings: Settings) -> None:
    with cliente(settings) as client:
        malo = client.post(
            "/api/v1/pacientes/1/cobros",
            json={"id_atencion": "1", "id_tutor": "abc"},
            headers=H,
        )
    assert malo.status_code == 422  # id_tutor solo admite digitos
