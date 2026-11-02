# Administración en dos niveles

Estado al 31 de octubre de 2026: **implementado en el backend** con la migración
`015_administracion_dos_niveles.sql`. El mockup sigue siendo una referencia visual.
El texto siguiente conserva la especificación que guio la implementación. Para los
contratos vigentes, campos, cursores, instalación y pruebas, consultar
[API del frontend de Hospital, Laboratorio y administración](api_frontend_hospital_laboratorio.md).

Precisiones respecto al plan original: la bitácora permite `establecimiento` nulo
para el cambio de contraseña propio del superusuario; su cursor es `id_evento`
descendente. La lectura de pagos por paciente también acepta el selector de entidad
de plataforma. La migración 016 completa los permisos del perfil hospitalario.

## 1. Decisiones

| | Superusuario | Administrador de la entidad |
| --- | --- | --- |
| Cuántos | **Uno** en toda la plataforma, sin institución. | **Uno activo por entidad** (ya existe). |
| Crear usuarios | En **cualquier** entidad, incluido el administrador de cada una. | Solo en **su** entidad. No crea administradores. |
| Deshabilitar y rehabilitar | Cualquier cuenta, salvo la suya. | Cuentas de su entidad que no sean de administración. |
| Eliminar | **Solo él**, como baja definitiva lógica. | No. |
| Permisos, área y contraseña | Cualquier cuenta, salvo la suya. | Cuentas de su entidad que no sean de administración (como hoy). |
| Datos clínicos | Ninguno. | Ninguno (como hoy). |
| Pagos | Solo lectura en Hospital General y Centro Pediátrico. | No. |
| Resumen | De las 4 entidades, solo conteos. | De su entidad: cuentas bloqueadas, deshabilitadas o pendientes de cambiar contraseña, personal por rol (y por área en el hospital) y últimos movimientos. |
| Bitácora de administración | Completa, de las 4 entidades. | Solo la de su entidad. |

Además:

* **Una entidad por cuenta**, como hoy. No se cambia después: para mover a alguien se
  crea una cuenta nueva en la otra entidad.
* **Eliminar es una baja definitiva lógica.** La cuenta:
  * no puede iniciar sesión ni volver a habilitarse;
  * sale de todos los listados;
  * conserva sus consultas, citas y entradas de bitácora;
  * mantiene reservado su correo.

  No se borra la fila, porque la referencian el historial clínico y
  `identidad.bitacora_profesionales`.
* **El correo de una cuenta eliminada no se libera.** Sigue reservado por `UNIQUE (correo)`.
* **No habrá superusuario de respaldo**, por ahora. Si pierde el acceso, se recupera con el
  script (§3.5).

## 2. Estado actual (lo que cambia)

* `app/domain/administracion.py` y `documentacion-backend.md` §0.4 y §3.8: un administrador
  por institución, que gestiona solo su institución (la del token). Esto **se conserva**.
* `database/postgresql/012_administracion_profesionales.sql`:
  * rol `administrador`;
  * *triggers* `validar_permiso_administrador()` y `validar_cambio_de_rol_administrador()`;
  * `bitacora_profesionales` con las acciones `alta`, `cambio`, `restablecer_contrasena`
    y `cambiar_contrasena`.
* `database/postgresql/002_identidad.sql`: `establecimiento NOT NULL` (una cuenta, un establecimiento).
* `app/infrastructure/identity/administracion.py`: las consultas filtran
  `establecimiento = institución del token AND rol <> 'administrador'`.
* `app/domain/identidad.py` y `app/infrastructure/identity/jwt.py`: `institucion` y el
  claim `inst` son obligatorios y se comparan en cada petición.
* No existe un endpoint para eliminar cuentas ni para crear administradores: el primer
  administrador se crea con `scripts/crear_profesional.py`.

## 3. Cambios propuestos

### 3.1 Base de datos: `015_administracion_dos_niveles.sql`

Migración aditiva e idempotente, como las anteriores.

1. **Rol `superusuario` sin establecimiento.**
   * `ALTER TABLE identidad.profesional ALTER COLUMN establecimiento DROP NOT NULL;`
   * Agregar `'superusuario'` a `ck_profesional_rol`.
   * `CHECK ((rol = 'superusuario') = (establecimiento IS NULL))`.
   * `ck_departamento_solo_hospital` no cambia: sin establecimiento, el área también queda nula.
2. **Unicidad.**
   * `CREATE UNIQUE INDEX ux_un_superusuario ON identidad.profesional ((rol)) WHERE rol = 'superusuario' AND eliminado_en IS NULL;`
   * `CREATE UNIQUE INDEX ux_un_admin_por_entidad ON identidad.profesional (establecimiento) WHERE rol = 'administrador' AND activo AND eliminado_en IS NULL;`
3. **Permiso propio del superusuario.**
   `INSERT INTO identidad.permiso(codigo) VALUES ('plataforma:administrar') ON CONFLICT DO NOTHING;`
4. **Triggers de permisos.** Reescribir `identidad.validar_permiso_administrador()`:
   * `administrador`: solo `profesionales:administrar`, como hoy;
   * `superusuario`: solo `plataforma:administrar` y `pagos:ver`;
   * nadie más puede tener `profesionales:administrar` ni `plataforma:administrar`.

   Extender `validar_cambio_de_rol_administrador()` a `superusuario`.
5. **Baja definitiva lógica.**
   * `ADD COLUMN IF NOT EXISTS eliminado_en TIMESTAMPTZ`, con
     `CHECK (eliminado_en IS NULL OR NOT activo)`.
   * Nuevo *trigger* `identidad.validar_reactivacion()`: si `OLD.eliminado_en IS NOT NULL`,
     rechaza poner `activo = TRUE` y volver a poner `eliminado_en` en nulo.
   * Agregar `'eliminar'` al `CHECK` de `bitacora_profesionales.accion`.
   * `GRANT UPDATE (eliminado_en) ON identidad.profesional TO historiales_app;`
6. **Bitácora.** Sin cambios de estructura. `establecimiento` es el de la cuenta afectada
   (siempre tiene uno); `id_actor` puede ser el superusuario o el administrador.
7. **Administradores existentes.** No se tocan: siguen funcionando igual.

### 3.2 Dominio

* `app/domain/permisos.py`
  * `PLATAFORMA_ADMINISTRAR = "plataforma:administrar"`.
  * `PERMISOS_POR_ROL["superusuario"] = {PLATAFORMA_ADMINISTRAR, PAGOS_VER}`.
* `app/domain/administracion.py`
  * `ROL_SUPERUSUARIO = "superusuario"`; actualizar el docstring a los dos niveles.
  * `EstadoCuenta.ELIMINADA` (se lee, pero no se puede asignar por `PATCH`).
  * `validar_rol(institucion, rol, *, actor_es_superusuario)`:
    * `superusuario` nunca por la API;
    * `administrador` solo si el actor es superusuario.
  * Nueva regla `puede_gestionar(actor, objetivo)`:
    * el superusuario gestiona cualquier cuenta menos la suya;
    * el administrador, solo cuentas de su entidad que no sean `administrador`.
  * `ROLES_POR_INSTITUCION`, `PERMISOS_ASIGNABLES`, `permisos_finales` y
    `validar_departamento` **no cambian**.
* `app/domain/identidad.py` y `app/domain/cuenta.py`: `institucion: Institucion | None`
  (`None` = plataforma), con una propiedad `es_plataforma`.

### 3.3 Identidad y token

* `app/infrastructure/identity/jwt.py`: el claim `inst` es `null` para el superusuario;
  la comparación de la línea ~82 acepta `None == None`.
* `app/infrastructure/identity/postgresql.py`:
  * leer `establecimiento` nulo;
  * una cuenta con `eliminado_en` no inicia sesión (mismo error que una inactiva, sin
    revelar el motivo).
* `app/infrastructure/identity/administracion.py`
  * Administrador: igual que hoy (entidad del token, sin cuentas de administración),
    excluyendo además las eliminadas.
  * Superusuario: filtra por la entidad recibida (opcional en el listado) e incluye a los
    administradores. Excluye siempre al superusuario y a las eliminadas.
  * Nuevo `eliminar(id_actor, id_profesional)`, en una transacción:
    * `activo = FALSE` y `eliminado_en = now()`;
    * incrementa la versión de token (cierra sus sesiones);
    * escribe la bitácora `eliminar`.

### 3.4 API

* `app/presentation/api/dependencies.py`
  * `GestorDeProfesionales`: acepta `profesionales:administrar` o `plataforma:administrar`.
  * `SuperusuarioDePlataforma`: exige `plataforma:administrar`.
  * `contexto_con_alguno`: si `usuario.institucion is None`, lanzar `AccesoDenegado` antes
    de abrir un motor. Es una segunda barrera: el superusuario no tiene permisos clínicos.
  * Nuevo `contexto_pagos_lectura(establecimiento)`: el superusuario elige la entidad;
    para cualquier otra cuenta se usa la del token. Solo acepta `hospital_general` y
    `centro_pediatrico` (otra → 422).
* `routes/profesionales.py`

| Endpoint | Administrador | Superusuario |
| --- | --- | --- |
| `POST /profesionales` | Su entidad; enviar `establecimiento` → 422. Rol `administrador` → 403. | `establecimiento` obligatorio. Rol `administrador` solo si la entidad no tiene uno activo (si no, 409). |
| `GET /profesionales?establecimiento=&rol=&estado=` | Su entidad, sin cuentas de administración. | Todas las entidades o la pedida, con administradores. Ninguno ve eliminadas. |
| `GET` y `PATCH /profesionales/{id}` | Su entidad, sin administradores (404). `estado`: `activa`, `bloqueada` o `inactiva`. | Cualquiera menos el superusuario; los mismos estados. |
| `POST /profesionales/{id}/restablecer-contrasena` | Su entidad, sin administradores. | Cualquiera menos el superusuario. |
| **Nuevo** `DELETE /profesionales/{id}` | **403** | Baja lógica, responde 204. 409 si ya estaba eliminada; 404 si es él mismo. |

  En el `PATCH`, `estado: eliminada` responde 422: eliminar solo se hace con `DELETE`.
  Una cuenta eliminada responde 409 a cualquier `PATCH`.
* `routes/cobros.py`: `GET /cobros`, `GET /servicios` y el `GET` de un cobro aceptan
  `?establecimiento=` para el superusuario. Los `POST` siguen con `ContextoRegistrarPagos`:
  el superusuario recibe 403.
* **Nuevo** `routes/plataforma.py`: `GET /plataforma/resumen` con `plataforma:administrar`.
  Devuelve **solo conteos** por entidad:
  * administrador activo (nombre);
  * personal activo y sin acceso;
  * pacientes registrados y citas de hoy;
  * camas ocupadas y emergencias (hospital);
  * cobros abiertos y saldos (hospital y pediátrico);
  * órdenes abiertas (laboratorio).

  Si un motor no responde, su entidad devuelve `null` y la respuesta sigue siendo válida.
* **Nuevo** `GET /profesionales/resumen` con `GestorDeProfesionales`: solo para la
  entidad del administrador; el superusuario la elige con `?establecimiento=`. Sale de
  `identidad.profesional` y no toca motores clínicos. Devuelve:
  * conteos por estado;
  * bloqueadas por intentos (`bloqueado_hasta` en el futuro y distinto de 9999-12-31);
  * pendientes de `debe_cambiar_contrasena`;
  * personal activo por rol y, en el hospital, por área;
  * las últimas 5 entradas de la bitácora.
* **Nuevo** `GET /profesionales/bitacora?establecimiento=&accion=&desde=&hasta=` con
  `GestorDeProfesionales`, paginado y ordenado del más reciente al más antiguo:
  * **alcance:** el administrador solo ve su entidad (enviar otra → 403); el
    superusuario, todas o la pedida;
  * **respuesta:** fecha, actor (nombre y rol, o «superusuario»), acción, cuenta
    afectada y `detalle`;
  * nunca devuelve contraseñas ni hashes, porque la tabla no los guarda.

  La tabla y su `GRANT SELECT` ya existen (012); solo falta el endpoint.
* `GET /auth/me`: `institucion: null` para el superusuario.

### 3.5 Scripts

* `scripts/crear_profesional.py`: `--rol superusuario` sin `--establecimiento`; falla si
  ya existe uno. `--rol administrador` se conserva para el arranque, aunque después el
  superusuario podrá crearlos por la API.

### 3.6 Pruebas

| Archivo | Qué agregar o cambiar |
| --- | --- |
| `tests/test_profesionales.py` | **Administrador:** 422 con `establecimiento` en el alta; 403 al crear un administrador; 404 al hacer `PATCH` sobre un administrador; deshabilitar y rehabilitar en su entidad; 403 en `DELETE`. **Superusuario:** alta en las 4 entidades; 422 con rol o permisos que no son de la entidad; crear un administrador y 409 si ya hay uno activo; `DELETE` y luego 409 al intentar rehabilitar. |
| `tests/test_identidad.py` | Token con `inst: null`; un token de plataforma no abre motores clínicos; una cuenta eliminada no inicia sesión y sus tokens quedan revocados. |
| `tests/test_cobros.py` | El superusuario lee con `?establecimiento=` del hospital y del pediátrico; 403 en los `POST`; 422 con laboratorio o clínica. |
| `tests/test_api.py` | 403 del superusuario y del administrador en `/pacientes`, `/citas`, órdenes y odontograma. |
| `tests/integration/test_administracion.py` | Índices (un superusuario, un administrador activo por entidad); *triggers* de permisos; una cuenta eliminada no se reactiva ni con SQL directo; bitácora `eliminar`. |
| Nuevo `tests/test_plataforma.py` | `GET /plataforma/resumen`: solo conteos, sin nombres ni ids de pacientes; un motor caído devuelve `null` para esa entidad; 403 para el administrador. |
| `tests/test_profesionales.py` (bitácora y resumen) | `GET /profesionales/bitacora`: el administrador ve solo su entidad y recibe 403 al pedir otra; el superusuario ve todas; filtros por acción y fechas; ninguna entrada trae contraseñas. `GET /profesionales/resumen`: distingue bloqueo por intentos de bloqueo administrativo; solo el hospital trae el desglose por área. |

### 3.7 Documentación

* `documentacion-backend.md`:
  * §0.4: dos niveles; el administrador de la entidad sigue igual, salvo que no elimina;
  * §3.8: parámetros nuevos de `/profesionales` y el `DELETE`;
  * tablas de permisos y roles (~líneas 326 y 338): agregar `plataforma:administrar`
    y `superusuario`;
  * descripción de la migración 015;
  * nueva sección para `/plataforma/resumen`.
* `docs/identidad_central.md`: el superusuario es la única cuenta sin establecimiento;
  procedimiento para crearlo y para recuperarlo si pierde el acceso.
* Docstrings de `app/domain/administracion.py` y `routes/profesionales.py`.

## 4. Orden sugerido

1. Migración 015 en una base de prueba, más las pruebas de integración de índices, *triggers* y baja lógica.
2. Dominio e identidad (`institucion` opcional, `puede_gestionar`, eliminada no inicia sesión).
3. `/profesionales` con el alcance por nivel, el `DELETE` lógico, `/profesionales/resumen` y `/profesionales/bitacora`.
4. Pagos en solo lectura y `/plataforma/resumen`.
5. Script del superusuario y documentación.

Los administradores actuales no necesitan migración de datos.

## 5. Riesgos

* **Cuenta de alto valor.** El superusuario es el único que elimina y crea
  administradores. Conviene sesión corta, cambio de contraseña obligatorio en el primer
  ingreso (`debe_cambiar_contrasena`) y, si es posible, un segundo factor.
* **Punto único de falla.** Si el superusuario pierde el acceso, solo el script puede
  crear otro. Documentarlo.
* **Eliminar por error.** Es irreversible por diseño. El mockup pide confirmación; la API
  podría exigir además el correo de la cuenta en el cuerpo del `DELETE`.
* **`institucion` opcional.** Es el cambio con más alcance. La barrera de 3.4 en
  `contexto_con_alguno` evita que un `None` llegue a una fábrica de repositorios.
* **Resumen sobre cuatro motores.** Usar tiempos límite y respuesta parcial, para que una
  entidad lenta no bloquee a las demás.

## 6. Decisiones tomadas en la revisión

* El correo de una cuenta eliminada **no** se libera.
* El superusuario **ve la bitácora** completa. El administrador ve la de su entidad: es lo
  mínimo para saber quién creó, deshabilitó o restableció cada cuenta.
* **Sin superusuario de respaldo** por ahora. El índice `ux_un_superusuario` ya lo impide.
