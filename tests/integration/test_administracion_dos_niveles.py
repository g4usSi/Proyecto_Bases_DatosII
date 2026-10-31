"""Administracion en dos niveles contra PostgreSQL real (migracion 015).

Crea cuentas sinteticas (@example.invalid) y las borra al terminar. Solo toca la identidad
central y el Hospital General (misma base): no necesita MongoDB ni Firestore. Si la base
local ya tiene un superusuario, las pruebas que lo crean se omiten para no tocarlo.
"""

from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from app.core.config import Settings
from app.main import create_app

CLAVE = "Clave-inicial-2026"
ENTIDADES = ("hospital_general", "centro_pediatrico", "laboratorio_clinico", "clinica_odontologica")


@pytest.fixture
def admin_pg(config_local):
    conexion = psycopg.connect(config_local["HISTORIALES_POSTGRES_ADMIN_DSN"], autocommit=True)
    yield conexion
    conexion.close()


@pytest.fixture
def plataforma(admin_pg):
    """Un superusuario sintetico y limpieza de todo lo que lleve la marca."""
    existente = admin_pg.execute(
        "SELECT 1 FROM identidad.profesional WHERE rol = 'superusuario' AND eliminado_en IS NULL"
    ).fetchone()
    if existente:
        pytest.skip("La base local ya tiene un superusuario; no se toca.")
    marca = uuid4().hex[:10]
    identificador = uuid4()
    correo = f"super-{marca}@example.invalid"
    admin_pg.execute(
        "INSERT INTO identidad.profesional (id_profesional, correo, nombres, apellidos, "
        "password_hash, establecimiento, rol) VALUES (%s, %s, 'Sara', 'Zzsuper', %s, NULL, "
        "'superusuario')",
        (identificador, correo, PasswordHash.recommended().hash(CLAVE)),
    )
    for permiso in ("plataforma:administrar", "pagos:ver"):
        admin_pg.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s, %s)", (identificador, permiso)
        )

    class Entorno:
        pass

    datos = Entorno()
    datos.marca = marca
    datos.id = str(identificador)
    datos.correo = correo
    datos.correo_de = lambda nombre: f"{nombre}-{marca}@example.invalid"
    yield datos

    ids = [
        f[0]
        for f in admin_pg.execute(
            "SELECT id_profesional FROM identidad.profesional WHERE correo LIKE %s",
            (f"%{marca}%",),
        )
    ]
    with admin_pg.transaction():
        admin_pg.execute("SET LOCAL session_replication_role = replica")
        admin_pg.execute(
            "DELETE FROM identidad.bitacora_profesionales "
            "WHERE id_profesional = ANY(%s) OR id_actor = ANY(%s)",
            (ids, ids),
        )
        admin_pg.execute(
            "DELETE FROM personal_medico WHERE id_profesional_central = ANY(%s)", (ids,)
        )
        admin_pg.execute("DELETE FROM identidad.profesional WHERE id_profesional = ANY(%s)", (ids,))


def entrar(client, correo, clave=CLAVE) -> dict[str, str]:
    respuesta = client.post("/api/v1/auth/login", json={"correo": correo, "password": clave})
    assert respuesta.status_code == 200, respuesta.text
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def entidad_sin_administrador(admin_pg) -> str | None:
    ocupadas = {
        f[0]
        for f in admin_pg.execute(
            "SELECT establecimiento FROM identidad.profesional WHERE rol = 'administrador' "
            "AND activo AND eliminado_en IS NULL"
        )
    }
    return next((e for e in ENTIDADES if e not in ocupadas), None)


def test_la_base_impone_los_dos_niveles(plataforma, admin_pg, config_local):
    # Un solo superusuario, siempre sin establecimiento y sin permisos clinicos.
    with pytest.raises(psycopg.errors.UniqueViolation):
        admin_pg.execute(
            "INSERT INTO identidad.profesional (id_profesional, correo, nombres, apellidos, "
            "password_hash, establecimiento, rol) VALUES (%s, %s, 'Otro', 'Zz', %s, NULL, "
            "'superusuario')",
            (uuid4(), plataforma.correo_de("super2"), PasswordHash.recommended().hash(CLAVE)),
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        admin_pg.execute(
            "UPDATE identidad.profesional SET establecimiento = 'hospital_general' "
            "WHERE id_profesional = %s",
            (plataforma.id,),
        )
    with pytest.raises(psycopg.errors.CheckViolation):
        admin_pg.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s, 'historiales:leer')",
            (plataforma.id,),
        )
    # Nadie mas puede tener plataforma:administrar.
    medico = uuid4()
    admin_pg.execute(
        "INSERT INTO identidad.profesional (id_profesional, correo, nombres, apellidos, "
        "password_hash, establecimiento, rol) VALUES (%s, %s, 'M', 'Zz', %s, "
        "'laboratorio_clinico', 'medico')",
        (medico, plataforma.correo_de("regla"), PasswordHash.recommended().hash(CLAVE)),
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        admin_pg.execute(
            "INSERT INTO identidad.profesional_permiso VALUES (%s, 'plataforma:administrar')",
            (medico,),
        )
    with pytest.raises(psycopg.errors.CheckViolation):  # sin entidad solo el superusuario
        admin_pg.execute(
            "UPDATE identidad.profesional SET establecimiento = NULL WHERE id_profesional = %s",
            (medico,),
        )
    # Baja definitiva: no se reactiva ni con SQL directo.
    admin_pg.execute(
        "UPDATE identidad.profesional SET activo = FALSE, eliminado_en = now() "
        "WHERE id_profesional = %s",
        (medico,),
    )
    for sentencia in (
        "UPDATE identidad.profesional SET activo = TRUE WHERE id_profesional = %s",
        "UPDATE identidad.profesional SET eliminado_en = NULL WHERE id_profesional = %s",
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            admin_pg.execute(sentencia, (medico,))
    # Un administrador activo por entidad.
    entidad = entidad_sin_administrador(admin_pg)
    if entidad is not None:
        for numero in (1, 2):
            fila = (
                uuid4(),
                plataforma.correo_de(f"adm{numero}"),
                PasswordHash.recommended().hash(CLAVE),
                entidad,
            )
            sentencia = (
                "INSERT INTO identidad.profesional (id_profesional, correo, nombres, apellidos, "
                "password_hash, establecimiento, rol) VALUES (%s, %s, 'A', 'Zz', %s, %s, "
                "'administrador')"
            )
            if numero == 1:
                admin_pg.execute(sentencia, fila)
            else:
                with pytest.raises(psycopg.errors.UniqueViolation):
                    admin_pg.execute(sentencia, fila)
    # La cuenta de la API no puede borrar ni cambiar el rol.
    app = psycopg.connect(config_local["HISTORIALES_POSTGRES_DSN"], autocommit=True)
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute("UPDATE identidad.profesional SET rol = 'superusuario'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            app.execute("DELETE FROM identidad.profesional")
    finally:
        app.close()


def test_flujo_del_superusuario_y_del_administrador(plataforma, admin_pg):
    entidad = entidad_sin_administrador(admin_pg)
    with TestClient(create_app(Settings())) as client:
        su = entrar(client, plataforma.correo)
        me = client.get("/api/v1/auth/me", headers=su).json()
        assert me["institucion"] is None and me["rol"] == "superusuario"
        assert me["permisos"] == ["pagos:ver", "plataforma:administrar"]
        # Sin datos clinicos: ni pacientes ni citas.
        assert client.get("/api/v1/pacientes/1", headers=su).status_code == 403
        assert client.get("/api/v1/citas/profesionales", headers=su).status_code == 403

        # Alta en el hospital: establecimiento obligatorio y perfil local vinculado.
        sin_entidad = client.post(
            "/api/v1/profesionales",
            json={
                "correo": plataforma.correo_de("x"),
                "nombres": "X",
                "apellidos": "Zz",
                "rol": "medico",
                "contrasena_inicial": CLAVE,
            },
            headers=su,
        )
        assert sin_entidad.status_code == 422
        alta = client.post(
            "/api/v1/profesionales",
            json={
                "correo": plataforma.correo_de("medico"),
                "nombres": "Mario",
                "apellidos": "Zzprueba",
                "rol": "medico",
                "establecimiento": "hospital_general",
                "contrasena_inicial": CLAVE,
            },
            headers=su,
        )
        assert alta.status_code == 201, alta.text
        medico = alta.json()["profesional"]
        assert alta.json()["vinculado"] is True and medico["institucion"] == "hospital_general"
        assert admin_pg.execute(
            "SELECT estado FROM personal_medico WHERE id_profesional_central = %s",
            (medico["id_profesional"],),
        ).fetchone() == ("Activo",)

        if entidad is not None:
            cuenta_admin = client.post(
                "/api/v1/profesionales",
                json={
                    "correo": plataforma.correo_de("admin"),
                    "nombres": "Ada",
                    "apellidos": "Zzadmin",
                    "rol": "administrador",
                    "establecimiento": entidad,
                    "contrasena_inicial": CLAVE,
                },
                headers=su,
            )
            assert cuenta_admin.status_code == 201, cuenta_admin.text
            assert cuenta_admin.json()["vinculado"] is None
            assert cuenta_admin.json()["profesional"]["permisos"] == ["profesionales:administrar"]
            segundo = client.post(
                "/api/v1/profesionales",
                json={
                    "correo": plataforma.correo_de("admin2"),
                    "nombres": "Bea",
                    "apellidos": "Zzadmin",
                    "rol": "administrador",
                    "establecimiento": entidad,
                    "contrasena_inicial": CLAVE,
                },
                headers=su,
            )
            assert segundo.status_code == 409 and "administrador activo" in segundo.text

            # El administrador: solo su entidad, sin cuentas de administracion, sin DELETE.
            adm = entrar(client, plataforma.correo_de("admin"))
            assert client.get(
                "/api/v1/profesionales", params={"establecimiento": "hospital_general"}, headers=adm
            ).status_code == (200 if entidad == "hospital_general" else 403)
            propios = client.get("/api/v1/profesionales", headers=adm).json()
            assert all(p["institucion"] == entidad and p["rol"] != "administrador" for p in propios)
            assert (
                client.delete(
                    f"/api/v1/profesionales/{medico['id_profesional']}", headers=adm
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/v1/profesionales",
                    json={
                        "correo": plataforma.correo_de("y"),
                        "nombres": "Y",
                        "apellidos": "Zz",
                        "rol": "administrador",
                        "contrasena_inicial": CLAVE,
                    },
                    headers=adm,
                ).status_code
                == 403
            )
            resumen = client.get("/api/v1/profesionales/resumen", headers=adm)
            assert resumen.status_code == 200 and resumen.json()["institucion"] == entidad
            assert resumen.json()["administrador"] == "Ada Zzadmin"

        # El superusuario ve a todos (con administradores) y nunca se ve a si mismo.
        todos = client.get("/api/v1/profesionales", headers=su).json()
        assert medico["id_profesional"] in [p["id_profesional"] for p in todos]
        assert plataforma.id not in [p["id_profesional"] for p in todos]
        assert client.get(f"/api/v1/profesionales/{plataforma.id}", headers=su).status_code == 404
        assert (
            client.delete(f"/api/v1/profesionales/{plataforma.id}", headers=su).status_code == 404
        )

        # Baja definitiva: no entra, no se rehabilita, sale de los listados, conserva el correo.
        medico_h = entrar(client, plataforma.correo_de("medico"))
        ruta = f"/api/v1/profesionales/{medico['id_profesional']}"
        assert client.patch(ruta, json={"estado": "eliminada"}, headers=su).status_code == 422
        assert client.delete(ruta, headers=su).status_code == 204
        assert client.get("/api/v1/auth/me", headers=medico_h).status_code == 401
        respuesta = client.post(
            "/api/v1/auth/login",
            json={"correo": plataforma.correo_de("medico"), "password": CLAVE},
        )
        assert respuesta.status_code == 401
        assert client.delete(ruta, headers=su).status_code == 409
        assert client.patch(ruta, json={"estado": "activa"}, headers=su).status_code == 409
        assert client.get(ruta, headers=su).json()["estado"] == "eliminada"
        lista = client.get(
            "/api/v1/profesionales", params={"establecimiento": "hospital_general"}, headers=su
        ).json()
        assert medico["id_profesional"] not in [p["id_profesional"] for p in lista]
        repetido = client.post(
            "/api/v1/profesionales",
            json={
                "correo": plataforma.correo_de("medico"),
                "nombres": "M",
                "apellidos": "Zz",
                "rol": "medico",
                "establecimiento": "hospital_general",
                "contrasena_inicial": CLAVE,
            },
            headers=su,
        )
        assert repetido.status_code == 409  # el correo sigue reservado
        assert admin_pg.execute(
            "SELECT estado FROM personal_medico WHERE id_profesional_central = %s",
            (medico["id_profesional"],),
        ).fetchone() == ("Inactivo",)

        # Bitacora: el superusuario ve todo, con filtros; nunca contrasenas.
        bitacora = client.get(
            "/api/v1/profesionales/bitacora", params={"accion": "eliminar"}, headers=su
        )
        assert bitacora.status_code == 200
        eliminacion = next(
            e for e in bitacora.json() if e["id_profesional"] == medico["id_profesional"]
        )
        assert eliminacion["actor_rol"] == "superusuario"
        assert eliminacion["institucion"] == "hospital_general"
        assert CLAVE not in bitacora.text and "argon2" not in bitacora.text
        hospital = client.get(
            "/api/v1/profesionales/resumen",
            params={"establecimiento": "hospital_general"},
            headers=su,
        ).json()
        assert hospital["activos_por_area"] is not None

        # Resumen de plataforma: solo conteos; un motor sin configurar sale como null.
        resumen = client.get("/api/v1/plataforma/resumen", headers=su)
        assert resumen.status_code == 200, resumen.text
        por_entidad = {e["institucion"]: e for e in resumen.json()["entidades"]}
        assert set(por_entidad) == set(ENTIDADES)
        hospital = por_entidad["hospital_general"]["indicadores"]
        assert hospital["pacientes_registrados"] >= 0 and hospital["camas_total"] is not None
        assert "nombres" not in resumen.text and "id_paciente" not in resumen.text

        # Pagos: solo lectura y eligiendo la entidad.
        assert client.get("/api/v1/cobros", headers=su).status_code == 422
        assert (
            client.get(
                "/api/v1/cobros", params={"establecimiento": "laboratorio_clinico"}, headers=su
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/v1/cobros", params={"establecimiento": "hospital_general"}, headers=su
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/pacientes/1/cobros", json={"id_atencion": "1"}, headers=su
            ).status_code
            == 403
        )


def test_el_superusuario_cambia_su_contrasena_sin_entidad(plataforma, admin_pg):
    """El superusuario cambia su propia contrasena: la bitacora acepta la entrada sin entidad."""
    with TestClient(create_app(Settings())) as client:
        su = entrar(client, plataforma.correo)
        cambio = client.post(
            "/api/v1/auth/cambiar-contrasena",
            json={"contrasena_actual": CLAVE, "contrasena_nueva": "Otra-clave-super-88"},
            headers=su,
        )
        assert cambio.status_code == 200, cambio.text
        su = {"Authorization": f"Bearer {cambio.json()['access_token']}"}
        propias = client.get(
            "/api/v1/profesionales/bitacora", params={"accion": "cambiar_contrasena"}, headers=su
        ).json()
    entrada = next(e for e in propias if e["id_profesional"] == plataforma.id)
    assert entrada["institucion"] is None
