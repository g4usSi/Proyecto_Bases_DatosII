"""Administracion de profesionales y cambio de contrasena, con dobles (sin motores)."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.container import Contenedor
from app.core.config import Settings
from app.domain import administracion as reglas
from app.domain.cuenta import CuentaProfesional, Sesion
from app.domain.errores import DatosInvalidos
from app.domain.identidad import UsuarioAutenticado
from app.domain.institucion import Institucion
from app.main import create_app
from tests.doubles import (
    AutenticadorDoble,
    CifradorDoble,
    DirectorioAdministrableDoble,
    UnidadTrabajoDoble,
)

AUTH = {"Authorization": "Bearer admin"}
CLAVE = "Clave-segura-2026"
ADMIN = UsuarioAutenticado(
    "a0000000-0000-4000-8000-000000000001",
    Institucion.HOSPITAL_GENERAL,
    frozenset({"profesionales:administrar"}),
    "Ada",
    "Admin",
    "administrador",
)


class CuentasDobles:
    """DirectorioProfesionales + InicioSesion minimos para cambiar la contrasena."""

    def __init__(self, directorio: DirectorioAdministrableDoble) -> None:
        self.directorio = directorio
        self.fallos = 0

    def _cuenta(self, ficha) -> CuentaProfesional:
        return CuentaProfesional(
            ficha.id_profesional,
            ficha.correo,
            self.directorio.contrasenas[ficha.id_profesional],
            ficha.institucion,
            ficha.permisos,
            0,
            True,
        )

    def buscar_por_id(self, id_profesional: str):
        ficha = self.directorio.fichas.get(id_profesional)
        return self._cuenta(ficha) if ficha else None

    def buscar_por_correo(self, correo: str):
        return next(
            (self._cuenta(f) for f in self.directorio.fichas.values() if f.correo == correo), None
        )

    def registrar_login(self, id_profesional: str, exitoso: bool) -> None:
        self.fallos += 0 if exitoso else 1

    def revocar_sesiones(self, id_profesional: str) -> None:
        pass

    def iniciar_sesion(self, correo: str, password: str) -> Sesion:
        cuenta = self.buscar_por_correo(correo)
        assert cuenta and cuenta.password_hash == "hash:" + password
        return Sesion("token-nuevo", 1800, cuenta.usuario())

    def cerrar_sesion(self, id_profesional: str) -> None:
        pass


def preparar(settings: Settings, usuarios=None, institucion=Institucion.HOSPITAL_GENERAL):
    directorio = DirectorioAdministrableDoble()
    unidad = UnidadTrabajoDoble({})
    cuentas = CuentasDobles(directorio)
    usuarios = usuarios or {"admin": replace(ADMIN, institucion=institucion)}
    contenedor = Contenedor(
        autenticador=AutenticadorDoble(usuarios),
        inicio_sesion=cuentas,
        cuentas=cuentas,
        administracion=directorio,
        cifrador=CifradorDoble(),
        unidades_trabajo={institucion: lambda: unidad},
    )
    return TestClient(create_app(settings, contenedor)), directorio, unidad, cuentas


def alta(client, **extra):
    cuerpo = {
        "correo": "Nuevo.Medico@Example.com ",
        "nombres": "Nuevo",
        "apellidos": "Medico",
        "rol": "medico",
        "contrasena_inicial": CLAVE,
    } | extra
    return client.post("/api/v1/profesionales", json=cuerpo, headers=AUTH)


def test_alta_con_permisos_base_y_perfil_local(settings: Settings) -> None:
    client, directorio, unidad, _ = preparar(settings)
    with client:
        respuesta = alta(client, permisos=["historiales:leer", "consultas:registrar"])
    assert respuesta.status_code == 201
    assert respuesta.headers["cache-control"] == "no-store"
    cuerpo = respuesta.json()
    ficha = cuerpo["profesional"]
    assert ficha["correo"] == "nuevo.medico@example.com"
    assert ficha["institucion"] == "hospital_general"  # del token, no del formulario
    assert ficha["permisos"] == ["consultas:registrar", "historiales:leer", "pacientes:leer"]
    assert ficha["debe_cambiar_contrasena"] is True
    assert CLAVE not in respuesta.text and "hash" not in respuesta.text
    assert cuerpo["contrasena_temporal"] is None
    assert cuerpo["vinculado"] is True
    assert unidad.profesionales.registros[ficha["id_profesional"]].rol == "medico"
    assert directorio.contrasenas[ficha["id_profesional"]] == "hash:" + CLAVE
    assert directorio.bitacora_eventos[-1][2] == "alta"


def test_alta_sin_contrasena_genera_una_que_cumple_la_politica(settings: Settings) -> None:
    client, directorio, _, _ = preparar(settings)
    with client:
        respuesta = alta(client, contrasena_inicial=None)
    temporal = respuesta.json()["contrasena_temporal"]
    assert respuesta.status_code == 201 and temporal
    reglas.validar_contrasena(temporal)
    assert directorio.contrasenas[respuesta.json()["profesional"]["id_profesional"]] == (
        "hash:" + temporal
    )


@pytest.mark.parametrize(
    ("extra", "texto"),
    [
        ({"rol": "secretaria"}, "Rol no valido"),
        ({"rol": "superusuario"}, "scripts/crear_profesional"),
        ({"establecimiento": "centro_pediatrico"}, "tu institucion"),
        ({"permisos": ["profesionales:administrar"]}, "exclusivo"),
        ({"permisos": ["laboratorio:validar"]}, "no aplican"),
        ({"contrasena_inicial": "corta-1"}, None),
        ({"contrasena_inicial": "abcdefghijklmn"}, "combinar"),
        ({"contrasena_inicial": "nuevo.medico-2026"}, "correo"),
        ({"correo": "sin-arroba"}, "Correo"),
    ],
)
def test_alta_rechaza_datos_incompatibles(settings: Settings, extra, texto) -> None:
    client, directorio, _, _ = preparar(settings)
    with client:
        respuesta = alta(client, **extra)
    assert respuesta.status_code == 422
    if texto:
        assert texto in str(respuesta.json())
    assert directorio.fichas == {}


def test_area_solo_en_el_hospital_y_secretaria_sin_permisos_clinicos(settings: Settings) -> None:
    client, _, _, _ = preparar(settings, institucion=Institucion.CLINICA_ODONTOLOGICA)
    with client:
        con_area = alta(client, rol="odontologo", id_departamento=1)
        secretaria_clinica = alta(
            client, rol="secretaria", correo="s@example.com", permisos=["historiales:leer"]
        )
        secretaria = alta(client, rol="secretaria", correo="s@example.com")
    assert con_area.status_code == 422 and "Hospital General" in con_area.text
    assert secretaria_clinica.status_code == 422
    assert secretaria.status_code == 201
    assert secretaria.json()["profesional"]["permisos"] == [
        "citas:gestionar",
        "citas:leer",
        "pacientes:leer",
        "pacientes:registrar",
    ]


def test_correo_repetido_es_409(settings: Settings) -> None:
    client, _, _, _ = preparar(settings)
    with client:
        assert alta(client).status_code == 201
        assert alta(client, correo="NUEVO.medico@example.com").status_code == 409


def test_solo_el_administrador_y_sin_acceso_clinico(settings: Settings) -> None:
    medico = UsuarioAutenticado(
        "m1", Institucion.HOSPITAL_GENERAL, frozenset({"pacientes:leer", "historiales:leer"})
    )
    client, _, _, _ = preparar(settings, {"admin": ADMIN, "medico": medico})
    with client:
        assert alta(client).status_code == 201
        medico_h = {"Authorization": "Bearer medico"}
        assert client.get("/api/v1/profesionales", headers=medico_h).status_code == 403
        assert client.post("/api/v1/profesionales", json={}, headers=medico_h).status_code in (
            403,
            422,
        )
        # El administrador no tiene permisos clinicos: no ve pacientes.
        assert client.get("/api/v1/pacientes/1", headers=AUTH).status_code == 403


def test_listar_consultar_y_aislamiento_por_institucion(settings: Settings) -> None:
    otro_admin = replace(ADMIN, id_usuario="otro", institucion=Institucion.CENTRO_PEDIATRICO)
    client, _, _, _ = preparar(settings, {"admin": ADMIN, "otro": otro_admin})
    with client:
        creado = alta(client).json()["profesional"]
        lista = client.get("/api/v1/profesionales", params={"rol": "medico"}, headers=AUTH)
        uno = client.get(f"/api/v1/profesionales/{creado['id_profesional']}", headers=AUTH)
        ajeno = client.get(
            f"/api/v1/profesionales/{creado['id_profesional']}",
            headers={"Authorization": "Bearer otro"},
        )
        vacia = client.get("/api/v1/profesionales", params={"rol": "enfermeria"}, headers=AUTH)
    assert [p["id_profesional"] for p in lista.json()] == [creado["id_profesional"]]
    assert uno.json() == creado
    assert ajeno.status_code == 404  # otra institucion: como si no existiera
    assert vacia.json() == []


def test_cambiar_permisos_estado_y_area(settings: Settings) -> None:
    client, directorio, unidad, _ = preparar(settings)
    with client:
        creado = alta(client, id_departamento=3).json()["profesional"]
        ruta = f"/api/v1/profesionales/{creado['id_profesional']}"
        permisos = client.patch(ruta, json={"permisos": ["citas:leer"]}, headers=AUTH)
        estado = client.patch(ruta, json={"estado": "inactiva"}, headers=AUTH)
        sin_area = client.patch(ruta, json={"id_departamento": None}, headers=AUTH)
        vacio = client.patch(ruta, json={}, headers=AUTH)
        invalido = client.patch(ruta, json={"estado": "jubilada"}, headers=AUTH)
    assert permisos.json()["profesional"]["permisos"] == ["citas:leer", "pacientes:leer"]
    assert permisos.json()["vinculado"] is None  # el perfil local no cambio
    assert estado.json()["profesional"]["estado"] == "inactiva"
    assert estado.json()["vinculado"] is True
    assert unidad.profesionales.registros[creado["id_profesional"]].activo is False
    assert (
        creado["id_departamento"] == 3 and sin_area.json()["profesional"]["id_departamento"] is None
    )
    assert vacio.status_code == 422 and invalido.status_code == 422
    assert [a for _, _, a in directorio.bitacora_eventos].count("cambio") == 3


def test_restablecer_muestra_la_contrasena_una_vez(settings: Settings) -> None:
    client, directorio, _, _ = preparar(settings)
    with client:
        creado = alta(client).json()["profesional"]
        ruta = f"/api/v1/profesionales/{creado['id_profesional']}/restablecer-contrasena"
        respuesta = client.post(ruta, headers=AUTH)
        inexistente = client.post(
            "/api/v1/profesionales/no-existe/restablecer-contrasena", headers=AUTH
        )
    nueva = respuesta.json()["contrasena_temporal"]
    assert respuesta.status_code == 200 and respuesta.headers["cache-control"] == "no-store"
    assert directorio.contrasenas[creado["id_profesional"]] == "hash:" + nueva
    assert directorio.fichas[creado["id_profesional"]].debe_cambiar_contrasena is True
    assert directorio.bitacora_eventos[-1][2] == "restablecer_contrasena"
    assert inexistente.status_code == 404


def test_cambiar_mi_contrasena(settings: Settings) -> None:
    client, directorio, _, cuentas = preparar(settings)
    with client:
        creado = alta(client).json()["profesional"]
        yo = UsuarioAutenticado(creado["id_profesional"], Institucion.HOSPITAL_GENERAL)
        client.app.state.contenedor.autenticador.usuarios["yo"] = yo
        mio = {"Authorization": "Bearer yo"}
        ruta = "/api/v1/auth/cambiar-contrasena"
        mala = client.post(
            ruta,
            json={"contrasena_actual": "otra-cosa-123", "contrasena_nueva": "Nueva-clave-99"},
            headers=mio,
        )
        igual = client.post(
            ruta, json={"contrasena_actual": CLAVE, "contrasena_nueva": CLAVE}, headers=mio
        )
        bien = client.post(
            ruta,
            json={"contrasena_actual": CLAVE, "contrasena_nueva": "Nueva-clave-99"},
            headers=mio,
        )
    assert mala.status_code == 422 and cuentas.fallos == 1
    assert igual.status_code == 422
    assert bien.status_code == 200 and bien.json()["access_token"] == "token-nuevo"
    assert bien.headers["cache-control"] == "no-store"
    assert directorio.contrasenas[creado["id_profesional"]] == "hash:Nueva-clave-99"
    assert directorio.fichas[creado["id_profesional"]].debe_cambiar_contrasena is False


def test_me_incluye_perfil_y_aviso_de_cambio(settings: Settings) -> None:
    usuario = replace(ADMIN, debe_cambiar_contrasena=True)
    client, _, _, _ = preparar(settings, {"admin": usuario})
    with client:
        me = client.get("/api/v1/auth/me", headers=AUTH).json()
    assert me["nombres"] == "Ada" and me["rol"] == "administrador"
    assert me["debe_cambiar_contrasena"] is True


def test_selector_de_profesionales_para_citas(settings: Settings) -> None:
    secretaria = UsuarioAutenticado(
        "s1", Institucion.HOSPITAL_GENERAL, frozenset({"pacientes:leer", "citas:leer"})
    )
    client, _, _, _ = preparar(settings, {"admin": ADMIN, "sec": secretaria})
    with client:
        alta(client)
        lista = client.get("/api/v1/citas/profesionales", headers={"Authorization": "Bearer sec"})
        sin_permiso = client.get("/api/v1/citas/profesionales", headers=AUTH)
    assert [p["nombres"] for p in lista.json()] == ["Nuevo"]
    assert set(lista.json()[0]) == {
        "id_profesional",
        "nombres",
        "apellidos",
        "rol",
        "id_departamento",
    }  # sin correo ni permisos
    assert sin_permiso.status_code == 403


def test_departamentos_solo_en_el_hospital(settings: Settings) -> None:
    client, _, _, _ = preparar(settings)
    with client:
        respuesta = client.get("/api/v1/departamentos", headers=AUTH)
    # El doble no es el hospital: responde como cualquier motor que no lo implementa.
    assert respuesta.status_code == 501


@pytest.mark.parametrize(
    "contrasena",
    ["corta-1", "  Espacios-al-inicio1", "aaaaaaaaaaaaa1", "x" * 129 + "1"],
)
def test_politica_de_contrasena(contrasena: str) -> None:
    with pytest.raises(DatosInvalidos):
        reglas.validar_contrasena(contrasena)


def test_contrasena_generada_es_aleatoria_y_valida() -> None:
    generadas = {reglas.generar_contrasena() for _ in range(20)}
    assert len(generadas) == 20
    for contrasena in generadas:
        reglas.validar_contrasena(contrasena)


# ---------------------------------------------------------------------------------------
# Administracion en dos niveles (docs/administracion_general.md)
# ---------------------------------------------------------------------------------------

SUPER = UsuarioAutenticado(
    "50000000-0000-4000-8000-000000000001",
    None,
    frozenset({"plataforma:administrar", "pagos:ver"}),
    "Sara",
    "Super",
    "superusuario",
)
SU = {"Authorization": "Bearer su"}


def preparar_dos_niveles(settings: Settings):
    """Superusuario + administrador del pediatrico, con motores dobles en las 4 entidades."""
    directorio = DirectorioAdministrableDoble()
    unidades = {i: UnidadTrabajoDoble({}) for i in Institucion}
    admin_ped = replace(ADMIN, id_usuario="adm-ped", institucion=Institucion.CENTRO_PEDIATRICO)
    contenedor = Contenedor(
        autenticador=AutenticadorDoble({"su": SUPER, "admin": admin_ped}),
        administracion=directorio,
        cifrador=CifradorDoble(),
        unidades_trabajo={i: (lambda u=u: u) for i, u in unidades.items()},
    )
    return TestClient(create_app(settings, contenedor)), directorio, unidades


def alta_su(client, establecimiento, **extra):
    return client.post(
        "/api/v1/profesionales",
        json={
            "correo": extra.pop("correo", f"{establecimiento}.{extra.get('rol', 'x')}@example.com"),
            "nombres": "Nueva",
            "apellidos": "Cuenta",
            "rol": "medico",
            "contrasena_inicial": CLAVE,
            "establecimiento": establecimiento,
        }
        | extra,
        headers=SU,
    )


def test_superusuario_crea_en_cualquier_entidad_y_vincula_en_su_motor(settings: Settings) -> None:
    client, directorio, unidades = preparar_dos_niveles(settings)
    with client:
        sin_entidad = client.post(
            "/api/v1/profesionales",
            json={"correo": "a@example.com", "nombres": "A", "apellidos": "B", "rol": "medico"},
            headers=SU,
        )
        roles = {
            "hospital_general": "enfermeria",
            "centro_pediatrico": "medico",
            "laboratorio_clinico": "laboratorista",
            "clinica_odontologica": "secretaria",
        }
        altas = {e: alta_su(client, e, rol=r) for e, r in roles.items()}
        rol_ajeno = alta_su(client, "laboratorio_clinico", rol="odontologo", correo="o@example.com")
        permiso_ajeno = alta_su(
            client,
            "clinica_odontologica",
            rol="odontologo",
            correo="p@example.com",
            permisos=["pagos:ver"],
        )
    assert sin_entidad.status_code == 422
    for entidad, respuesta in altas.items():
        assert respuesta.status_code == 201, respuesta.text
        ficha = respuesta.json()["profesional"]
        assert ficha["institucion"] == entidad and respuesta.json()["vinculado"] is True
        assert ficha["id_profesional"] in unidades[Institucion(entidad)].profesionales.registros
    assert rol_ajeno.status_code == 422 and permiso_ajeno.status_code == 422
    assert all(actor == SUPER.id_usuario for actor, _, _ in directorio.bitacora_eventos)


def test_superusuario_crea_un_administrador_por_entidad(settings: Settings) -> None:
    client, _, _ = preparar_dos_niveles(settings)
    with client:
        primero = alta_su(client, "laboratorio_clinico", rol="administrador")
        segundo = alta_su(
            client, "laboratorio_clinico", rol="administrador", correo="otro@example.com"
        )
        con_permisos = alta_su(
            client,
            "hospital_general",
            rol="administrador",
            correo="h@example.com",
            permisos=["historiales:leer"],
        )
        superusuario = alta_su(
            client, "hospital_general", rol="superusuario", correo="s@example.com"
        )
    assert primero.status_code == 201
    assert primero.json()["profesional"]["permisos"] == ["profesionales:administrar"]
    assert primero.json()["vinculado"] is None  # sin perfil local
    assert segundo.status_code == 409
    assert con_permisos.status_code == 422
    assert superusuario.status_code == 422 and "scripts/crear_profesional" in superusuario.text


def test_alcance_del_administrador_frente_al_superusuario(settings: Settings) -> None:
    client, directorio, _ = preparar_dos_niveles(settings)
    with client:
        propio = alta_su(client, "centro_pediatrico").json()["profesional"]
        ajeno = alta_su(client, "hospital_general").json()["profesional"]
        admin_otro = alta_su(client, "hospital_general", rol="administrador").json()["profesional"]
        lista_admin = client.get("/api/v1/profesionales", headers=AUTH).json()
        otra_entidad = client.get(
            "/api/v1/profesionales", params={"establecimiento": "hospital_general"}, headers=AUTH
        )
        ver_ajeno = client.get(f"/api/v1/profesionales/{ajeno['id_profesional']}", headers=AUTH)
        lista_su = client.get("/api/v1/profesionales", headers=SU).json()
        filtrada = client.get(
            "/api/v1/profesionales", params={"establecimiento": "hospital_general"}, headers=SU
        ).json()
        rehabilitar = client.patch(
            f"/api/v1/profesionales/{propio['id_profesional']}",
            json={"estado": "inactiva"},
            headers=AUTH,
        )
        patch_admin = client.patch(
            f"/api/v1/profesionales/{admin_otro['id_profesional']}",
            json={"nombres": "X"},
            headers=AUTH,
        )
    assert [p["id_profesional"] for p in lista_admin] == [propio["id_profesional"]]
    assert otra_entidad.status_code == 403 and ver_ajeno.status_code == 404
    assert {p["id_profesional"] for p in lista_su} == {
        propio["id_profesional"],
        ajeno["id_profesional"],
        admin_otro["id_profesional"],
    }
    assert {p["id_profesional"] for p in filtrada} == {
        ajeno["id_profesional"],
        admin_otro["id_profesional"],
    }
    assert rehabilitar.status_code == 200 and patch_admin.status_code == 404
    assert directorio.fichas[propio["id_profesional"]].estado == "inactiva"


def test_eliminar_solo_el_superusuario_y_es_definitivo(settings: Settings) -> None:
    client, _, unidades = preparar_dos_niveles(settings)
    with client:
        cuenta = alta_su(client, "centro_pediatrico").json()["profesional"]
        ruta = f"/api/v1/profesionales/{cuenta['id_profesional']}"
        por_admin = client.delete(ruta, headers=AUTH)
        como_patch = client.patch(ruta, json={"estado": "eliminada"}, headers=SU)
        eliminar = client.delete(ruta, headers=SU)
        otra_vez = client.delete(ruta, headers=SU)
        rehabilitar = client.patch(ruta, json={"estado": "activa"}, headers=SU)
        restablecer = client.post(f"{ruta}/restablecer-contrasena", headers=SU)
        a_si_mismo = client.delete(f"/api/v1/profesionales/{SUPER.id_usuario}", headers=SU)
        listados = [client.get("/api/v1/profesionales", headers=h).json() for h in (SU, AUTH)]
        filtro_eliminadas = client.get(
            "/api/v1/profesionales", params={"estado": "eliminada"}, headers=SU
        )
    assert por_admin.status_code == 403
    assert como_patch.status_code == 422
    assert eliminar.status_code == 204 and otra_vez.status_code == 409
    assert rehabilitar.status_code == 409 and restablecer.status_code == 409
    assert a_si_mismo.status_code == 404
    assert all(
        cuenta["id_profesional"] not in [p["id_profesional"] for p in lista] for lista in listados
    )
    assert filtro_eliminadas.status_code == 422
    perfil = unidades[Institucion.CENTRO_PEDIATRICO].profesionales.registros
    assert perfil[cuenta["id_profesional"]].activo is False  # el perfil local queda inactivo


def test_bitacora_y_resumen_con_el_alcance_de_cada_nivel(settings: Settings) -> None:
    client, _, _ = preparar_dos_niveles(settings)
    with client:
        alta_su(client, "centro_pediatrico")
        alta_su(client, "hospital_general")
        de_admin = client.get("/api/v1/profesionales/bitacora", headers=AUTH)
        admin_otra = client.get(
            "/api/v1/profesionales/bitacora",
            params={"establecimiento": "hospital_general"},
            headers=AUTH,
        )
        de_su = client.get("/api/v1/profesionales/bitacora", headers=SU)
        solo_bajas = client.get(
            "/api/v1/profesionales/bitacora", params={"accion": "eliminar"}, headers=SU
        )
        resumen_admin = client.get("/api/v1/profesionales/resumen", headers=AUTH)
        resumen_su_sin = client.get("/api/v1/profesionales/resumen", headers=SU)
        resumen_su = client.get(
            "/api/v1/profesionales/resumen",
            params={"establecimiento": "hospital_general"},
            headers=SU,
        )
        medico = client.get(
            "/api/v1/profesionales/bitacora",
            headers={"Authorization": "Bearer medico"},
        )
    assert [e["institucion"] for e in de_admin.json()] == ["centro_pediatrico"]
    assert admin_otra.status_code == 403
    assert {e["institucion"] for e in de_su.json()} == {"centro_pediatrico", "hospital_general"}
    assert solo_bajas.json() == []
    assert resumen_admin.json()["institucion"] == "centro_pediatrico"
    assert resumen_admin.json()["activos_por_area"] is None
    assert resumen_su_sin.status_code == 422
    assert resumen_su.json()["activos_por_area"] == []
    assert medico.status_code == 401


def test_el_superusuario_no_abre_motores_clinicos(settings: Settings) -> None:
    client, _, _ = preparar_dos_niveles(settings)
    with client:
        me = client.get("/api/v1/auth/me", headers=SU).json()
        rutas = [
            client.get("/api/v1/pacientes/1", headers=SU),
            client.get("/api/v1/pacientes", params={"nombre": "ana"}, headers=SU),
            client.get("/api/v1/citas", headers=SU),
            client.get("/api/v1/citas/profesionales", headers=SU),
            client.get("/api/v1/laboratorio/ordenes", headers=SU),
            client.get("/api/v1/pacientes/1/odontograma", headers=SU),
        ]
        departamentos = client.get("/api/v1/departamentos", headers=SU)
    assert me["institucion"] is None and me["rol"] == "superusuario"
    assert {r.status_code for r in rutas} == {403}
    # El selector de areas abre el hospital (el doble no lo implementa: 501, no 403).
    assert departamentos.status_code == 501


def test_reglas_de_dominio_de_los_dos_niveles() -> None:
    otro_admin = replace(ADMIN, id_usuario="otro")
    ficha = reglas.FichaProfesional(
        "x",
        "x@example.com",
        "X",
        "Y",
        "medico",
        Institucion.HOSPITAL_GENERAL,
        reglas.EstadoCuenta.ACTIVA,
        frozenset(),
    )
    admin_ficha = replace(ficha, id_profesional="a", rol="administrador")
    super_ficha = replace(
        ficha, id_profesional=SUPER.id_usuario, rol="superusuario", institucion=None
    )
    assert reglas.puede_gestionar(ADMIN, ficha) and reglas.puede_gestionar(SUPER, ficha)
    assert not reglas.puede_gestionar(ADMIN, admin_ficha)
    assert reglas.puede_gestionar(SUPER, admin_ficha)
    assert not reglas.puede_gestionar(SUPER, super_ficha)
    assert not reglas.puede_gestionar(
        replace(otro_admin, institucion=Institucion.CENTRO_PEDIATRICO), ficha
    )
    assert reglas.alcance_de(SUPER) == reglas.Alcance(None, True)
    assert reglas.alcance_de(ADMIN) == reglas.Alcance(Institucion.HOSPITAL_GENERAL, False)
    with pytest.raises(DatosInvalidos):
        reglas.permisos_finales(
            Institucion.HOSPITAL_GENERAL, "medico", frozenset({"plataforma:administrar"})
        )
