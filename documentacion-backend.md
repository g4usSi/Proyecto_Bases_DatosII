# Documentación del backend

API de historiales clínicos (FastAPI, Python 3.12, arquitectura hexagonal) sobre **cuatro
motores de base de datos**. Identidad central en PostgreSQL; cada establecimiento guarda
sus propios pacientes en su propio motor.

| Establecimiento | Motor | Qué guarda |
| --- | --- | --- |
| Hospital General | PostgreSQL | Pacientes, historial, citas; identidad y cuentas de **todos** (esquema `identidad`). |
| Centro Pediátrico | MySQL 8.4 | Pacientes, historial, citas, crecimiento y vacunación. |
| Laboratorio Clínico | MongoDB 8 | Pacientes, historial, citas, catálogo de pruebas, órdenes, muestras y resultados. |
| Clínica Odontológica | Cloud Firestore | Pacientes, historial, citas (agenda), odontograma. |

Este documento explica **qué hace cada pieza**. Para arrancar el proyecto ver el
[README](README.md); para decisiones de modelado ver `docs/`.

---

## 0. Decisiones de diseño vigentes

Decisiones del equipo que condicionan el backend y el frontend. Están anotadas aquí para
no perderlas antes de implementar el cliente.

### 0.1 Los cuatro establecimientos están separados; solo comparten el login

* Lo **único central** es la identidad del personal (PostgreSQL, esquema `identidad`):
  correo, contraseña, permisos y a qué establecimiento pertenece cada profesional.
* **Los pacientes no se comparten ni se replican.** Cada establecimiento guarda solo los
  suyos en su propio motor. No existe un "paciente global" ni un índice común.
* Consecuencia: si Becca se atiende en el Laboratorio, el Hospital General y el Centro
  Pediátrico, **se registra una vez en cada uno** y tendrá tres expedientes e ids
  independientes. Nada de uno se ve desde otro (un profesional solo accede al motor de su
  establecimiento, nunca al de otro).
* Es lo que pide el enunciado (cuatro bases con motores distintos) y el motivo de la
  comparación entre motores. Si algún día se quisiera enlazar al mismo paciente entre
  establecimientos haría falta un identificador común (p. ej. DPI/CUI) o un índice central;
  **hoy no existe y no está planeado**.

### 0.2 Citas en el Laboratorio Clínico: función extra, no prioritaria

* El enunciado no pide citas para el laboratorio. El backend **las tiene implementadas**
  (colección `citas` en MongoDB, mismas rutas `/citas` que los demás) porque el contrato es
  común a los cuatro motores, pero se consideran una **funcionalidad extra**.
* **Decisión para el frontend:** no se prioriza una pantalla de agenda para el Laboratorio.
  Se construye primero lo esencial (login, pacientes, historial, consultas, órdenes y
  resultados). Si sobra tiempo se reutiliza la misma agenda de la clínica odontológica.
* No hay nada que quitar del backend: dejar las citas del laboratorio sin pantalla no
  afecta al resto. Las citas "reales" del enunciado son las de la Clínica Odontológica.

### 0.3 Centro Pediátrico: sin control de stock por lote

* El sistema **no maneja lotes ni existencias de vacunas**. Aplicar una dosis solo registra
  quién la aplicó, cuándo y las observaciones de reacción.
* Se eliminó la ruta `GET /vacunas/{id}/lotes`, el campo `id_lote` al aplicar y los campos
  `id_lote`/`lote` de la respuesta de dosis. Migración MySQL `010_sin_stock_vacunas.sql`.
* Se conserva el **catálogo de tipos de vacuna** (nombre, edad recomendada, dosis) porque
  el esquema recomendado depende de él. La tabla `catalogo_vacunas` (lotes) sigue en el
  esquema original pero la API ya no la usa.

---

## 1. Cómo funciona una petición

1. El cliente hace `POST /api/v1/auth/login` con correo y contraseña. Si es válido recibe un
   **JWT** (30 min por defecto).
2. En cada petición posterior envía `Authorization: Bearer <token>`.
3. La API verifica el token y **vuelve a leer al profesional en PostgreSQL** (activo,
   institución, permisos vigentes). Un permiso retirado o una cuenta bloqueada surte efecto
   en la siguiente petición, no al expirar el token.
4. El **motor se elige por la institución del profesional**, nunca por algo que mande el
   cliente. Un médico del Hospital General no puede tocar datos del Laboratorio.
5. La ruta exige un permiso (§4). Si falta → 403.
6. Se ejecuta un **caso de uso** dentro de una *unidad de trabajo*: o se confirma todo, o no
   se guarda nada (con las salvedades de MongoDB, §6.3).
7. Cada acción queda en la bitácora de auditoría (§8).

## 2. Arquitectura por capas

```text
app/
  domain/            Entidades y reglas puras (no conocen FastAPI ni ningún motor)
  application/
    ports/           Contratos (Protocol) que cada motor implementa
    use_cases/       Reglas comunes: existe, no archivado, estado válido, commit
  infrastructure/
    identity/        JWT y repositorio de identidad en PostgreSQL
    persistence/     Un adaptador por motor: postgresql/, mysql/, mongodb/, firestore/
  presentation/api/  Rutas HTTP, esquemas (Pydantic), dependencias de seguridad, errores
  bootstrap/         Contenedor: crea las conexiones y elige la unidad de trabajo
  core/              Configuración (Settings) y auditoría
```

Regla de oro: **las reglas que no dependen del motor viven en el caso de uso**, y el
adaptador solo guarda y lee de forma atómica. Así los cuatro motores se comportan igual
desde fuera.

### 2.1 Dominio (`app/domain`)

| Archivo | Qué contiene |
| --- | --- |
| `paciente.py` | `Paciente`, `NuevoPaciente`, `CambiosPaciente` (corrección de datos). |
| `consulta.py` | `Consulta`, diagnósticos, tratamientos, recetas y `Adenda` (nota posterior). |
| `cita.py` | Estados de cita (`programada`, `confirmada`, …), transiciones permitidas y cuáles ocupan horario. |
| `odontograma.py` | Piezas dentales y lista fija de 12 estados. |
| `pediatria.py` | Control de crecimiento, catálogo de vacunas y dosis (`pendiente/aplicada/cancelada`); cálculo de edad en meses. |
| `laboratorio.py` | Catálogo de pruebas con rangos de referencia, orden, muestra, resultado; interpretación bajo/normal/alto. |
| `permisos.py` | Permisos, roles y permisos vedados a la secretaria. |
| `profesional.py`, `cuenta.py`, `identidad.py`, `institucion.py` | Cuenta, estado de bloqueo, institución ↔ motor. |
| `errores.py` | Errores de negocio que la API traduce a códigos HTTP (§5). |

### 2.2 Puertos (`app/application/ports`)

`RepositorioPacientes`, `RepositorioHistorial`, `RepositorioCitas`, `RepositorioProfesionales`,
`RepositorioOdontograma`, `RepositorioCrecimiento`, `RepositorioVacunacion`,
`RepositorioLaboratorio` y `UnidadDeTrabajo` (agrupa los anteriores y ofrece `commit()`).
Lo que un motor no ofrece se resuelve con el repositorio *pendiente*
(`persistence/pendiente.py`), que responde **501**.

### 2.3 Casos de uso (`app/application/use_cases`)

| Archivo | Casos de uso |
| --- | --- |
| `registrar_paciente.py` | `RegistrarPaciente`. |
| `consultar_paciente.py`, `buscar_pacientes.py` | `ConsultarPaciente`, `BuscarPacientes` (por nombre, sin importar tildes ni mayúsculas). |
| `actualizar_paciente.py` | `ActualizarPaciente` (corrige nombre, contacto, etc.), `AgregarAlergias` (solo agrega, nunca borra). |
| `consultar_historial.py` | `ConsultarHistorial` (paginado, más reciente primero). |
| `registrar_consulta.py` | `RegistrarConsulta` (consulta + diagnósticos + tratamientos + recetas en una sola operación). |
| `agregar_a_consulta.py` | `ConsultarConsulta`, `AgregarAConsulta` (**adenda**: la consulta original no se modifica). |
| `archivar_paciente.py` | `ArchivarPaciente` (baja lógica; no se borra nada). |
| `citas.py` | `AgendarCita`, `ConsultarAgenda`, `CitasDePaciente`, `CambiarEstadoCita`. |
| `odontograma.py` | `ConsultarOdontograma`, `ActualizarPieza`. |
| `pediatria.py` | Crecimiento: `RegistrarControlCrecimiento`, `ConsultarCrecimiento`. Vacunación: `ConsultarCatalogoVacunas`, `ConsultarEsquema`, `ProgramarDosis`, `GenerarEsquemaRecomendado`, `AplicarDosis`, `CancelarDosis`. |
| `laboratorio.py` | `ConsultarCatalogoLaboratorio`, `SolicitarOrden`, `ConsultarOrdenes`, `RegistrarMuestra`, `RegistrarResultados`, `ValidarOrden`, `CancelarOrden`. |

Reglas comunes que aplican todos: el paciente debe existir (404) y **no estar archivado**
(409) para cualquier escritura; los datos se validan antes de tocar la base (422).

---

## 3. Endpoints

Prefijo `/api/v1` (configurable). Documentación interactiva en `/docs`.
**Motores**: PG = Hospital, MY = Pediátrico, MO = Laboratorio, FS = Odontológica, "todos"
= los cuatro. Donde dice "otros → 501" el motor no aplica y la API responde 501 explicando
a qué establecimiento corresponde.

### 3.1 Sistema (sin autenticación)

| Ruta | Qué hace |
| --- | --- |
| `GET /health` | Vivo: la aplicación responde. No toca bases de datos. |
| `GET /health/ready` | Listo: hace un *ping* a cada motor configurado. 200 si todos responden; 503 con el detalle por motor si alguno falla. No expone credenciales ni errores internos. |
| `GET /` | Nombre y versión de la API. |

### 3.2 Autenticación

| Ruta | Qué hace |
| --- | --- |
| `POST /auth/login` | Valida correo/contraseña (Argon2). Cuenta bloqueada tras intentos fallidos repetidos. Devuelve el JWT. |
| `POST /auth/logout` | Revoca **todas las sesiones** del profesional (los tokens emitidos dejan de valer). |
| `GET /auth/me` | Datos del profesional autenticado: institución, rol y permisos vigentes. |

### 3.3 Pacientes e historial (todos los motores)

| Ruta | Permiso | Qué hace |
| --- | --- | --- |
| `POST /pacientes` | `pacientes:registrar` | Registra un paciente (contacto y alergias son opcionales). |
| `GET /pacientes?nombre=&limite=` | `pacientes:leer` | Busca por nombre. |
| `GET /pacientes/{id}` | `pacientes:leer` | Ficha del paciente. Las alergias solo se muestran a quien tiene `historiales:leer`. |
| `PATCH /pacientes/{id}` | `pacientes:registrar` | Corrige datos personales (solo los campos enviados). |
| `POST /pacientes/{id}/alergias` | `pacientes:registrar` | Agrega alergias nuevas sin duplicar ni borrar las existentes. |
| `GET /pacientes/{id}/historial?limite=&antes_de=` | `historiales:leer` | Consultas del paciente, paginadas. |
| `POST /pacientes/{id}/consultas` | `consultas:registrar` | Registra una consulta con diagnósticos, tratamientos y recetas. Atómica. |
| `GET /pacientes/{id}/consultas/{id_consulta}` | `historiales:leer` | Una consulta con todo su detalle y adendas. |
| `POST /pacientes/{id}/consultas/{id_consulta}/adenda` | `consultas:registrar` | Agrega diagnósticos/tratamientos/recetas a una consulta **ya registrada**. Cada elemento queda rotulado con fecha y profesional. Es solo-agregar (append-only). |
| `POST /pacientes/{id}/archivo` | `historiales:archivar` | Archiva el historial (baja lógica). Un historial archivado rechaza nuevas consultas, citas y cambios con 409. |

### 3.4 Citas (todos los motores)

| Ruta | Permiso | Qué hace |
| --- | --- | --- |
| `POST /citas` | `citas:gestionar` | Agenda una cita. **Rechaza (409) si el profesional ya está ocupado en ese tramo**, aun con dos peticiones simultáneas. |
| `GET /citas?desde=&hasta=&id_profesional=` | `citas:leer` | Agenda por rango de fechas y profesional. |
| `GET /pacientes/{id}/citas` | `citas:leer` | Citas de un paciente. |
| `POST /citas/{id}/estado` | `citas:gestionar` | Cambia el estado según las transiciones permitidas (`programada → confirmada → atendida`, cancelada, etc.). Una transición inválida da 409. Cancelar libera el horario. |

### 3.5 Odontograma (solo Clínica Odontológica; otros → 501)

| Ruta | Permiso | Qué hace |
| --- | --- | --- |
| `GET /pacientes/{id}/odontograma` | `historiales:leer` | Estado de cada pieza dental. |
| `PUT /pacientes/{id}/odontograma/piezas/{pieza}` | `consultas:registrar` | Cambia el estado de una pieza. Solo valores de la lista fija (12), otro → 422. |

### 3.6 Pediatría (solo Centro Pediátrico; otros → 501)

| Ruta | Permiso | Qué hace |
| --- | --- | --- |
| `POST /pacientes/{id}/crecimiento` | `consultas:registrar` | Registra un control (peso, talla, perímetro cefálico). Los controles son **inmutables** (un trigger impide modificarlos o borrarlos): un error se corrige registrando un nuevo control y aclarándolo en `observaciones`. Se rechaza un control anterior al nacimiento o en un expediente archivado. |
| `GET /pacientes/{id}/crecimiento` | `historiales:leer` | Curva de controles. |
| `GET /vacunas` | `historiales:leer` | Catálogo de tipos de vacuna. |
| `GET /pacientes/{id}/vacunacion` | `historiales:leer` | Esquema de vacunación del paciente. |
| `POST /pacientes/{id}/vacunacion` | `consultas:registrar` | Programa una dosis. No permite duplicar la misma dosis de la misma vacuna. |
| `POST /pacientes/{id}/vacunacion/esquema-recomendado` | `consultas:registrar` | Genera las dosis pendientes según la edad del paciente (requiere fecha de nacimiento) y el catálogo. |
| `POST /pacientes/{id}/vacunacion/{id_dosis}/aplicar` | `consultas:registrar` | Marca la dosis como aplicada: guarda quién la aplicó (el usuario de la sesión), cuándo y las `observaciones_reaccion` (opcional). Una dosis aplicada ya no se modifica. **Sin lotes ni stock** (§0.3). |
| `POST /pacientes/{id}/vacunacion/{id_dosis}/cancelar` | `consultas:registrar` | Cancela una dosis pendiente. |

### 3.7 Laboratorio (solo Laboratorio Clínico; otros → 501)

Flujo de una orden: `solicitada → en_proceso → validada` (o `cancelada`).

| Ruta | Permiso | Qué hace |
| --- | --- | --- |
| `GET /laboratorio/pruebas` | `historiales:leer` **o** `laboratorio:resultados` | Catálogo de pruebas activas con parámetros y rangos. |
| `POST /pacientes/{id}/ordenes` | `consultas:registrar` | El clínico solicita pruebas. La orden guarda **una copia** de la prueba y sus rangos: cambiar el catálogo después no reinterpreta órdenes antiguas. |
| `GET /pacientes/{id}/ordenes` | `historiales:leer` **o** `laboratorio:resultados` | Órdenes del paciente. |
| `GET /pacientes/{id}/ordenes/{id_orden}` | ídem | Una orden con muestras y resultados. |
| `POST /pacientes/{id}/ordenes/{id_orden}/muestras` | `laboratorio:resultados` | Registra la muestra tomada. Pasa la orden a `en_proceso`. |
| `PUT /pacientes/{id}/ordenes/{id_orden}/pruebas/{codigo}/resultados` | `laboratorio:resultados` | Captura resultados; cada valor se interpreta (bajo/normal/alto) contra el rango copiado en la orden. Se pueden corregir mientras la orden no esté validada. |
| `POST /pacientes/{id}/ordenes/{id_orden}/validar` | `laboratorio:validar` | Valida la orden. Desde ese momento es **inmutable**. Exige que todas las pruebas tengan resultado. |
| `POST /pacientes/{id}/ordenes/{id_orden}/cancelar` | `consultas:registrar` | Cancela una orden aún abierta. |

---

## 4. Permisos y roles

| Permiso | Permite |
| --- | --- |
| `pacientes:leer` | Buscar y ver fichas. |
| `pacientes:registrar` | Registrar, corregir datos, agregar alergias. |
| `historiales:leer` | Ver historial, consultas, alergias, odontograma, crecimiento, vacunas, resultados. |
| `consultas:registrar` | Registrar consultas y adendas, odontograma, controles, dosis, solicitar/cancelar órdenes. |
| `historiales:archivar` | Archivar historiales. |
| `citas:leer` / `citas:gestionar` | Ver / agendar y cambiar estado de citas. |
| `laboratorio:resultados` | Registrar muestras y capturar resultados. |
| `laboratorio:validar` | Validar órdenes. |

Los permisos se asignan **por profesional** (tabla en PostgreSQL), no por rol. El rol solo
fija los valores por defecto al crear la cuenta:

* **laboratorista**: `pacientes:leer`, `laboratorio:resultados`, `laboratorio:validar`.
* **secretaria** (solo existe en la Clínica Odontológica): `pacientes:leer`,
  `pacientes:registrar`, `citas:leer`, `citas:gestionar`. **No puede** tener permisos
  clínicos ni archivar; está bloqueado en el script, en triggers y en un `CHECK` de
  PostgreSQL. No cuenta como profesional de atención.
* Otros roles (`medico`, `enfermeria`, `odontologo`): por defecto solo `pacientes:leer`; el
  resto se concede con `--permiso`.

## 5. Códigos de respuesta

| Código | Cuándo |
| --- | --- |
| 401 | Sin token, token inválido/expirado/revocado, credenciales incorrectas. |
| 403 | Falta el permiso, cuenta inactiva o bloqueada. |
| 404 | Paciente, cita, consulta, orden o dosis inexistente (también si pertenece a otra institución). |
| 409 | Paciente archivado, horario ocupado, transición de estado inválida, orden ya validada, dosis que ya no está pendiente. |
| 422 | Datos inválidos (formato, rangos, estado de pieza fuera de la lista, etc.). |
| 501 | La operación no aplica a ese motor (odontograma, pediatría, laboratorio). |
| 503 | Motor no disponible o integración sin configurar. |

---

## 6. Cada motor

### 6.1 PostgreSQL — Hospital General + identidad

Migraciones en `database/postgresql/` (se aplican en orden):

| Archivo | Contenido |
| --- | --- |
| `001_hospital_general.sql` | Esquema original del hospital. |
| `002_identidad.sql` | Esquema `identidad`: profesionales, cuentas, permisos, sesiones. |
| `003_vinculo_profesional.sql` | Vincula cuenta con el personal médico de la institución. |
| `004_permisos.sql` | Cuenta limitada de la API (mínimo privilegio). |
| `005_proteger_login.sql` | Bloqueo por intentos fallidos. |
| `006_rol_secretaria_citas.sql` | Rol secretaria y permisos de citas. |
| `007_secretaria_restricciones.sql` | Triggers y `CHECK` que vedan permisos clínicos a la secretaria. |
| `008_escritura_api.sql` | Escrituras de la API, `unaccent`, permisos por columna. |
| `009_citas_adendas_edicion.sql` | Citas con restricción de no-solape (`EXCLUDE USING gist`), adendas, edición de pacientes. |
| `010_integridad_hospital.sql` | Reglas de integridad que faltaban del esquema original. |
| `011_permisos_laboratorio.sql` | Permisos `laboratorio:resultados` y `laboratorio:validar`. |

Consistencia: una transacción por petición; `EXCLUDE gist` impide citas solapadas aunque
dos peticiones lleguen a la vez; *advisory locks* y `FOR SHARE` serializan la baja contra
una consulta simultánea; triggers protegen datos inmutables.
Pagos y camas del esquema original tienen sus reglas en la base pero **no tienen API**.

### 6.2 MySQL — Centro Pediátrico

Archivos en `database/mysql/` (001, 002, 004, 006, 008 son esquema; 003, 005, 007, 009 son
permisos de la cuenta limitada).

| Archivo | Contenido |
| --- | --- |
| `001`, `002` | Esquema revisado e integridad (saldos, facturación; el stock de vacunas ya no se usa, ver 010). |
| `003`, `005` | Cuenta `historiales_app` con permisos mínimos. |
| `004` | Columnas para las escrituras de la API. |
| `006` | Citas, adendas, edición de datos, restricciones. |
| `007` | Permisos de esas extensiones. |
| `008_pediatria.sql` | `control_crecimiento` y reglas: triggers `control_validar_insert`, `control_inmutable`, `control_conservar_delete`. |
| `009_permisos_pediatria.sql` | `SELECT/INSERT` en controles; `UPDATE` por columna en `esquema_vacunacion`. |
| `010_sin_stock_vacunas.sql` | Quita el descuento de stock y la exigencia de lote al aplicar una dosis (triggers y `CHECK` de `esquema_vacunacion`). Idempotente. |

Consistencia: `FOR UPDATE`/`FOR SHARE` en las filas del paciente, la dosis y la agenda; los
triggers lanzan `SIGNAL 45000` y el adaptador (`_traducir_trigger`) los convierte en
errores de negocio (409/422).

### 6.3 MongoDB — Laboratorio Clínico

Todo en `laboratorio_clinico_mongo.js` (6 colecciones con validadores e índices):
`pacientes`, `profesionales` (con `rol`), `catalogo_pruebas`, `consultas`,
**`citas`** y `ordenes_laboratorio` (cada orden lleva embebidas sus muestras y resultados).

Consistencia (servidor único, **sin transacciones multi-documento**):

* Las operaciones se acumulan como cierres (`pendientes`) y se ejecutan en `commit()`.
* Las actualizaciones son **condicionales** por estado (p. ej. "solo si la orden no está
  validada"), de modo que dos peticiones simultáneas se serializan en Mongo.
* La baja del paciente (`estado: Activo`) es el punto de serialización contra consultas.
* Citas: índice único parcial `uq_cita_sin_choques` sobre `bloques`; cada minuto ocupado
  genera una clave `<profesional>|<minuto>`. Granularidad: **1 minuto**.
* Las adendas usan un *pipeline* con `$literal` para evitar inyección de operadores.
* Limitación: el usuario `readWrite` de la app no se puede restringir a solo-agregar;
  el validador solo garantiza estado y resultados.

### 6.4 Firestore — Clínica Odontológica

Colecciones por paciente con subcolecciones de consultas y odontograma, más
`agendas/{profesional}_{fecha}` para las citas.

* Escrituras múltiples con `WriteBatch`.
* Lectura-modificación-escritura con `@firestore.transactional` (citas, baja, adendas).
* Al agendar se verifica que el paciente siga activo; al cancelar/descartar una cita se
  libera el horario en la agenda.
* Los permisos de Firestore se controlan con la cuenta de servicio (IAM), no con SQL.

---

## 7. Seguridad

* **Contraseñas** con Argon2; **bloqueo** de la cuenta tras intentos fallidos
  (`005_proteger_login.sql`); mensajes de error iguales para correo inexistente y
  contraseña incorrecta.
* **JWT** con emisor, audiencia y caducidad; revocación de sesiones en logout; permisos releídos en
  cada petición.
* **Mínimo privilegio**: las cuentas de base de datos de la API no tienen `DELETE`; el
  `UPDATE` es por columna donde el motor lo permite. Las credenciales administrativas
  nunca se pasan a la API (solo a los scripts).
* **Aislamiento institucional**: el motor y las consultas salen de la institución del
  token verificado, no de la petición.
* **Inmutabilidad clínica**: consultas solo se amplían con adendas; controles de
  crecimiento no se editan; órdenes validadas no cambian; nada se borra (el archivo es
  baja lógica).
* **Sin inyección**: consultas parametrizadas en SQL; en Mongo/Firestore no se
  construyen filtros con texto del cliente.
* CORS cerrado por defecto (`HISTORIALES_CORS_ORIGINS=[]`).

## 8. Auditoría y salud

* **Auditoría** (`app/core/auditoria.py`, logger `auditoria`): por petición registra
  usuario, institución, método, plantilla de ruta (no la URL con ids), permiso exigido e
  id del paciente. **Nunca** datos clínicos. Los accesos denegados se registran como
  `WARNING`.
* **`/health`** indica que el proceso vive; **`/health/ready`** comprueba cada motor.

---

## 9. Scripts (`scripts/`)

| Script | Qué hace |
| --- | --- |
| `configurar_desarrollo.py` | Genera `.env` con contraseñas aleatorias sin sobrescribir valores existentes. |
| `crear_profesional.py` | Alta de un profesional (correo, institución, rol, `--permiso` repetible). Pide la contraseña por consola. Valida las reglas de la secretaria. |
| `sincronizar_profesionales.py` | Copia los profesionales activos de PostgreSQL al motor de su institución (MongoDB guarda también el `rol`). |
| `cargar_catalogos.py` | `vacunas ARCHIVO.json` y `laboratorio ARCHIVO.json [--desactivar-anteriores]`. Carga catálogos con conexión administrativa. Vacunas: solo tipos (sin lotes). Laboratorio: una (código, versión) publicada es inmutable. |
| `probar_firestore.py` | Comprueba la conexión a Firestore. |

Catálogos de ejemplo en `database/ejemplos/` (**datos DEMO, no de uso clínico**).

## 10. Configuración (variables `HISTORIALES_*`)

| Variable | Uso |
| --- | --- |
| `POSTGRES_DSN` + `JWT_SECRET` | Obligatorias juntas (identidad). `JWT_SECRET` ≥ 32 bytes. |
| `POSTGRES_ADMIN_DSN` | Solo scripts; **no** pasar a la API. |
| `MYSQL_HOST/PORT/USER/PASSWORD/DATABASE` | Centro Pediátrico. |
| `MONGODB_URI`, `MONGODB_DATABASE` | Laboratorio Clínico. |
| `FIRESTORE_CREDENTIALS`, `FIRESTORE_PROJECT_ID`, `FIRESTORE_DATABASE` | Clínica Odontológica. Con `FIRESTORE_EMULATOR_HOST` usa el emulador. |
| `ZONA_HORARIA` | Zona de las agendas (por defecto `America/Guatemala`). |
| `ACCESS_TOKEN_MINUTES`, `CORS_ORIGINS`, `API_PREFIX`, `LOG_LEVEL`, `ENVIRONMENT` | Comportamiento general. |

Un motor sin configurar no impide arrancar: sus rutas responden 503.
Las fechas se guardan en UTC; en PostgreSQL la cita guarda además fecha y hora local según
`ZONA_HORARIA`.

## 11. Pruebas

```powershell
python -m pytest                       # unitarias con dobles (sin bases de datos)
python -m ruff check .
python -m ruff format --check .

$env:HISTORIALES_TEST_INTEGRATION = '1'   # integración real
python -m pytest
```

* Unitarias: reglas, permisos, rutas y errores con repositorios en memoria (`tests/doubles.py`).
* Integración por motor: PostgreSQL, MySQL (base temporal creada y eliminada por la
  suite, con la cuenta limitada), MongoDB y Firestore, incluyendo **concurrencia** (dos
  bajas, consulta vs. baja, dos citas en el mismo horario, validar vs. editar resultado).
* Firestore: con `FIRESTORE_EMULATOR_HOST=127.0.0.1:8686` corre contra el emulador; sin
  esa variable usa la clave real.
* Las pruebas usan datos sintéticos y los eliminan al terminar. No usar con datos reales.

## 12. Docker

`docker compose --profile api up -d --build` levanta PostgreSQL, MySQL, MongoDB y la API.
Los scripts SQL/JS se montan y se ejecutan solo al crear un volumen **vacío**. Para un
volumen existente hay que aplicar las migraciones nuevas a mano (ver §14).

---

## 13. Qué faltaba y qué se agregó

Barrido de los cuatro modelos contra el enunciado del curso:

| Hallazgo | Solución |
| --- | --- |
| Las consultas no se podían ampliar sin modificarlas. | Adendas append-only (`AgregarAConsulta`) en los 4 motores. |
| No había forma de corregir un dato del paciente ni agregar alergias. | `PATCH /pacientes/{id}` y `POST .../alergias`. |
| Citas solo existían en Firestore. | Citas con no-solape en PostgreSQL, MySQL, MongoDB y Firestore. |
| El Centro Pediátrico no usaba su modelo de crecimiento y vacunas. | Módulo de pediatría (crecimiento y vacunación; sin control de stock, ver §0.3). |
| El Laboratorio no tenía órdenes, muestras ni resultados. | Módulo de laboratorio con interpretación y validación. |
| Faltaban reglas de integridad del esquema original de PostgreSQL. | Migración `010`. |
| Sin auditoría. | Bitácora `auditoria`. |
| Sin comprobación de disponibilidad de las bases. | `/health/ready`. |
| Catálogos sin forma de cargarse. | `scripts/cargar_catalogos.py` y ejemplos DEMO. |
| `compose.yaml` no montaba las migraciones nuevas. | Montajes añadidos. |

## 14. Cómo aplicar los cambios a bases ya creadas

* **PostgreSQL**: ejecutar con la cuenta administradora, en orden, `009`, `010` y `011`.
* **MySQL**: ejecutar `006`, `007`, `008`, `009` y `010` (las de esquema como administrador, las
  de permisos igual) en la base `hospital_pediatrico`. La `010` es la que quita el stock.
* **MongoDB**: volver a ejecutar `laboratorio_clinico_mongo.js` (crea la colección `citas`
  y actualiza validadores e índices sin borrar datos).
* **Firestore**: no requiere migración.
* Después: `python -m scripts.sincronizar_profesionales` para que MongoDB guarde el `rol`.

## 15. Límites conocidos

* Lo nuevo de Firestore (citas de agenda, adendas, edición) se probó con el **emulador**; no se repitió contra el proyecto real.
* El arranque desde cero con Docker no se ejecutó; sí se verificó la inicialización de
  los scripts contra motores locales equivalentes.
* Pagos y camas del Hospital General tienen reglas en la base pero no endpoints.
* No hay API para cambiar contraseñas ni administrar profesionales: se hace con scripts.
* MongoDB sin *replica set*: no hay transacciones; queda una ventana de milisegundos entre
  una consulta y una baja simultáneas (las actualizaciones condicionales la acotan).
* Granularidad de agenda en MongoDB: 1 minuto.
* Crecimiento y vacunación solo en MySQL; laboratorio solo en MongoDB; odontograma solo en
  Firestore (por diseño).
* La duplicidad de una dosis de vacuna se valida en el caso de uso, no con una restricción
  de la base.
* Los catálogos DEMO no son de grado clínico.
