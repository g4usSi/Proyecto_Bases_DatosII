# API para el mockup: Hospital General, Laboratorio y administracion

Revision del 31 de octubre de 2026. Referencia visual:
`docs/referencia/Historiales identidad visual.html`. Todas las rutas de este documento
usan el prefijo `/api/v1`, autenticacion Bearer y datos persistidos. El HTML sigue siendo
una maqueta: este trabajo completa el backend que consumira el frontend.

## Distribucion por ramas

La administracion general y los indicadores de cobros forman una base comun presente
en `Hospital-General` y `Laboratorio-Clinico`. Las atenciones, el grupo sanguineo,
el perfil propio y la migracion 016 pertenecen a `Hospital-General`. El resumen y
el desempate del cursor de ordenes pertenecen a `Laboratorio-Clinico`. Esta guia
describe el contrato combinado: al integrar ambas ramas se obtiene todo el alcance.
Las pruebas especificas del Hospital estan en `test_frontend_hospital.py`; las del
Laboratorio, en `test_mongodb_api.py`. Los comandos de integracion se pueden acotar
a los archivos presentes en cada rama.

## Correspondencia con las pantallas

| Pantalla | Rutas que la alimentan |
| --- | --- |
| Hospital: Inicio | `GET /hospital/resumen`, `GET /departamentos`, `GET /citas`, `GET /ingresos?tipo=emergencia&abiertos=true`. Importes: `GET /cobros/resumen`, solo con `pagos:ver`. |
| Hospital: Emergencias | `GET /ingresos?tipo=emergencia&abiertos=true`, detalle y alta bajo `/pacientes/{id}/ingresos/{id_ingreso}`. El tiempo transcurrido lo calcula el cliente. |
| Hospital: Camas | `GET /departamentos`, `GET /camas?id_departamento=&estado=`, `POST /camas/{id}/estado`, `POST /pacientes/{id}/ingresos`. |
| Hospital: Atenciones | **Nuevo:** `GET /atenciones`, `GET /pacientes/{id}/atenciones`, `GET /pacientes/{id}/atenciones/{id_atencion}`. |
| Hospital: Pulsera | `GET /pacientes/{id}` incluye `grupo_sanguineo`. **Nuevo:** `PUT /pacientes/{id}/grupo-sanguineo`. |
| Mi perfil | **Nuevo:** `GET /auth/perfil`; datos centrales y, en Hospital, colegiado, especialidades, telefono y estado local. |
| Hospital: Pagos | `/servicios`, `/cobros`, **nuevo:** `/cobros/resumen` y operaciones bajo `/pacientes/{id}/cobros/{id_cobro}`. Los endpoints de escritura existentes se conservan. |
| Laboratorio: Tablero | `GET /laboratorio/ordenes?estado=&limite=&antes_de=&antes_de_id=`; **nuevo:** `GET /laboratorio/resumen`. |
| Laboratorio: Resultados | Crear/consultar orden, registrar muestras, capturar resultados, validar y cancelar bajo `/pacientes/{id}/ordenes/{id_orden}`. Ya existian: no se duplican. |
| Laboratorio: Catalogo y versiones | `GET /laboratorio/pruebas`, `GET /laboratorio/pruebas/{codigo}/versiones`. Catalogo de solo lectura, cargado con `scripts.cargar_catalogos`. |
| Administracion de la entidad | `/profesionales`, **nuevos:** `/profesionales/resumen` y `/profesionales/bitacora`. |
| Administracion general | Las mismas rutas de personal con alcance de plataforma, **nuevo:** `DELETE /profesionales/{id}` y `GET /plataforma/resumen`. Pagos de solo lectura con `?establecimiento=`. |

## Hospital: contratos nuevos

### Atenciones

Permiso: `historiales:leer`. Solo Hospital; las otras instituciones responden 501.

`GET /atenciones` acepta `tipo=CONSULTA|INGRESO`, `desde`, `hasta` (ISO 8601 con zona),
`limite` (1–200, por defecto 50) y `antes_de` (ID numerico de la ultima fila).
El intervalo es `[desde, hasta)`. `desde >= hasta` devuelve 422.
Se ordena por ID descendente: las atenciones registradas mas recientemente primero.
El listado por paciente tambien acepta `limite` y `antes_de`.

Cada fila contiene `id_atencion`, `tipo`, `id_paciente`, `nombre_paciente`,
`id_profesional`, `nombre_profesional`, `fecha_hora`, `motivo`, `id_cita`, `cama`,
`tipo_ingreso`, `alta_en`, `id_cobro` y `estado_cobro`. Los campos que no aplican son
`null`. Una atencion con varios cobros anulados aparece una sola vez; se prioriza el
cobro vigente. No se devuelven montos.

El detalle devuelve `{atencion, consulta, ingreso}`: `consulta` o `ingreso` contiene
el contrato existente completo, y el otro es `null`. Esto permite dibujar el recorrido
con diagnosticos, recetas, ordenes y alta. Un ID de atencion de otro paciente da 404.
Para montos, el frontend consulta el cobro con `pagos:ver`.

### Grupo sanguineo

`PUT /pacientes/{id}/grupo-sanguineo` exige `consultas:registrar`:

```json
{"grupo_sanguineo": "O+"}
```

Acepta `A+`, `A-`, `B+`, `B-`, `AB+`, `AB-`, `O+`, `O-` o `null` para dejarlo sin dato.
El campo es obligatorio en el cuerpo; 422 si falta o es invalido, 409 si el expediente
esta archivado. Devuelve `{id_paciente, grupo_sanguineo}`. El registro comun de paciente
no cambia: una vez creado, se puede guardar el grupo con esta ruta. En la ficha el grupo
se oculta (`null`) a cuentas sin `historiales:leer`, igual que las alergias.

### Perfil propio

`GET /auth/perfil` no recibe un ID ajeno. Devuelve:

```json
{
  "usuario": {"id_usuario": "...", "institucion": "hospital_general", "permisos": [], "nombres": "...", "apellidos": "...", "rol": "medico", "debe_cambiar_contrasena": false},
  "correo": "profesional@example.invalid",
  "hospital": {"colegiado": null, "especialidades": [], "telefono": null, "estado": "Activo"}
}
```

`hospital` es `null` fuera del Hospital, para administradores o si no existe perfil local.
Los campos sin informacion no se inventan. La respuesta lleva `Cache-Control: no-store`.

### Indicadores de cobros

`GET /cobros/resumen` exige `pagos:ver`. Devuelve `cobros_por_estado`,
`saldo_pendiente`, `cobrado_hoy`, `pagos_anulados` y `cobrado_hoy_por_metodo`.
Estados, saldo y pagos anulados son globales; los cobros de hoy usan el dia local
configurado y excluyen pagos anulados. Los montos viajan como texto decimal.
No se calculan sumando la pagina visible del tablero. Tambien aplica a Pediatrico,
donde los estados no soportados y pagos anulados son cero. El superusuario elige
`?establecimiento=` igual que en los otros GET de cobros.

## Laboratorio: conteos y paginacion

`GET /laboratorio/resumen` exige `historiales:leer` o `laboratorio:resultados` y devuelve
`solicitada`, `en_proceso`, `validada`, `cancelada` y `listas_para_validar` (enteros).
La ultima cuenta ordenes abiertas con resultados en todas sus pruebas, segun la misma
regla de validacion existente. Estos conteos corresponden a toda la institucion, no
solo a las primeras 50 filas del tablero. No contienen valores de resultados.

Para paginar el tablero sin perder fechas empatadas se envian **ambos** valores de la
ultima fila: `antes_de=<solicitada_en>&antes_de_id=<id_orden>`. `antes_de_id` debe ser un
ObjectId de 24 caracteres hexadecimales y requiere `antes_de` (422 si no). El cursor
anterior, solo por fecha, sigue admitido por compatibilidad.

El catalogo y sus versiones ya estaban implementados. Cada orden conserva la copia
del catalogo y sus rangos; no se cambian resultados historicos al publicar otra version.
Una orden validada o cancelada sigue siendo inmutable.

## Administracion general y de entidad

La institucion de un administrador sigue saliendo del token. Solo el superusuario tiene
`institucion: null` y los permisos `plataforma:administrar`, `pagos:ver`. El administrador
tiene exclusivamente `profesionales:administrar`. Ninguno tiene acceso clinico.

### Usuarios

| Accion | Administrador de entidad | Superusuario |
| --- | --- | --- |
| `POST /profesionales` | Su entidad; enviar `establecimiento`, incluso `null`, da 422. Crear administrador da 403. | Debe enviar `establecimiento`. Puede crear personal y administradores. |
| `GET /profesionales?establecimiento=&rol=&id_departamento=&estado=&limite=` | Su entidad, sin administradores. Otra entidad da 403. | Todas o la indicada, incluidos administradores. |
| `GET/PATCH /profesionales/{id}` y restablecer contrasena | Su entidad, sin administradores (404). | Cualquier cuenta institucional. El superusuario no se administra por estas rutas (404). |
| `DELETE /profesionales/{id}` | 403. | 204: baja definitiva logica, revoca sesiones y registra evento. |

Hay un superusuario y un administrador **activo** por entidad; la base impone la
unicidad incluso con peticiones concurrentes (409). Una cuenta eliminada desaparece
de listados y del selector de citas; GET da 404, PATCH o repetir DELETE da 409.
Conserva correo reservado, historial y bitacora. No se puede rehabilitar ni con SQL.
`PATCH {"estado":"eliminada"}` da 422; los estados asignables son `activa`, `bloqueada`,
`inactiva`. Cambiar una cuenta de institucion no esta permitido.

### Resumen y bitacora del personal

`GET /profesionales/resumen`: el administrador obtiene su entidad; el superusuario
debe elegir `?establecimiento=`. Devuelve `por_estado`, `bloqueadas_por_intentos`,
`pendientes_cambio_contrasena`, `activos_por_rol`, `activos_por_departamento` (solo
Hospital; `null` en las otras) y `ultimos_movimientos` (5). Se distingue el bloqueo
temporal del administrativo, representado por 9999-12-31.

`GET /profesionales/bitacora` admite `establecimiento`, `accion`, `desde`, `hasta`,
`limite` (1–200, por defecto 50), `antes_de` (id_evento de la ultima fila).
Orden descendente de `id_evento`; fechas con zona, intervalo `[desde,hasta)`.
Acciones: `alta`, `cambio`, `restablecer_contrasena`, `cambiar_contrasena`, `eliminar`.
Cada entrada tiene `id_evento`, `ocurrido_en`, `institucion`, `actor`, `rol_actor`,
`id_profesional`, `cuenta`, `accion`, `detalle`. Nunca devuelve contrasenas ni hashes.
Un administrador ve solo su entidad; el superusuario todas o la elegida. El cambio de
contrasena propio del superusuario tiene `institucion: null`.

### Resumen de plataforma y pagos

`GET /plataforma/resumen` exige `plataforma:administrar`. Devuelve un objeto con las
cuatro claves institucionales. Cada entidad tiene `administrador_activo` (nombre),
`personal_activo`, `personal_sin_acceso`, `pacientes_registrados`, `citas_hoy`, y segun
sus capacidades: `camas_ocupadas`, `emergencias_abiertas`, `cobros_abiertos`,
`saldo_pendiente`, `ordenes_abiertas`. Nunca devuelve fichas ni IDs de pacientes.
Un motor no configurado, no disponible o que no termine en 15 segundos devuelve
`null` para su entidad; las otras conservan sus resultados. No es una transaccion
ni una fotografia simultanea de los cuatro motores.

El superusuario consulta las areas con `GET /departamentos?establecimiento=hospital_general`
(sin el parametro u otra entidad da 422), para asignarlas al crear o editar personal.

El superusuario usa `?establecimiento=hospital_general|centro_pediatrico` en los GET
de cobros, servicios y cobros de paciente. Omitirlo u ofrecer otra entidad da 422.
Todos los POST de pagos/cobros dan 403 para plataforma. Para otras cuentas, el alcance
siempre es su institucion; pedir otra da 403. El catalogo `/servicios` sigue siendo
exclusivo del Hospital (501 en Pediatrico).

## Instalacion y verificacion

En volumenes nuevos, Compose monta las migraciones PostgreSQL **015 y 016**.
En un volumen existente, aplicar primero las migraciones anteriores que falten, y luego:

```powershell
Get-Content database/postgresql/015_administracion_dos_niveles.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
Get-Content database/postgresql/016_frontend_hospital.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
```

Repetir el script MongoDB con la cuenta administrativa para actualizar validadores e
indices, sin borrar documentos. MySQL necesita las migraciones y permisos existentes
hasta 014 para sus funciones administrativas y de pagos; no se modifica su modelo aqui.

Crear la unica cuenta de plataforma (la contrasena se pide sin mostrarla):

```powershell
python -m scripts.crear_profesional --rol superusuario --correo superusuario@example.invalid --nombres Administracion --apellidos General
```

No se indica institucion. El primer ingreso solicita cambiar la contrasena en el
frontend mediante `debe_cambiar_contrasena`. Si pierde acceso, un operador local puede
usar `python -m scripts.restablecer_superusuario`, con `HISTORIALES_POSTGRES_ADMIN_DSN`.
No se crea otra cuenta de respaldo ni se publica una contrasena fija.

Verificacion reproducible con PostgreSQL y MySQL temporales (se eliminan al terminar)
y los datos sinteticos de las fixtures MongoDB:

```powershell
python -m pytest --ignore=tests/integration
python -m scripts.probar_backend_temporal tests/integration/test_frontend_contratos.py tests/integration/test_hospital.py tests/integration/test_administracion.py tests/integration/test_mongodb_api.py
python -m ruff check app scripts tests
python -m ruff format --check app scripts tests
python -m pip check
```

La agregacion de Firestore esta implementada con `count()`. Su verificacion contra
cloud requiere las credenciales de esa entidad; si no estan configuradas, la plataforma
devuelve `null` para la Clinica. No se conectan datos simulados al mockup.
