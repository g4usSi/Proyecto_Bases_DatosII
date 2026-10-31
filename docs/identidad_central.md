# Identidad central

Decisión del equipo: exclusivamente profesionales de la salud y un establecimiento
por profesional. PostgreSQL contiene el esquema `identidad`, separado del esquema
clínico `public` del Hospital General. MySQL, MongoDB y posteriormente Firestore
guardan sus propios datos clínicos. La API es el punto de acceso común.

1. Una herramienta administrativa crea el profesional con UUID, correo normalizado,
   hash Argon2id, rol, establecimiento y permisos explícitos.
2. `POST /api/v1/auth/login` recibe solamente correo y contraseña en JSON. El
   cliente no puede elegir establecimiento ni motor.
3. PostgreSQL entrega la institución vinculada y la API emite un JWT HS256 firmado
   con vigencia de 30 minutos por defecto, emisor y audiencia definidos.
4. En cada solicitud se valida firma/vencimiento y se vuelve a consultar el estado,
   establecimiento, permisos y versión de sesión en PostgreSQL. No confiar en
   permisos almacenados en el token.
5. La fábrica resuelve el repositorio clínico por esa institución verificada.

El JWT contiene identificador, institución, versión y metadatos de sesión; no
incluye información clínica, correo ni hash. La clave permanece en `.env`, ignorado
por Git. El generador produce secretos aleatorios y conserva valores existentes.
La API usa una cuenta PostgreSQL limitada, no la cuenta administrativa de altas.

`POST /auth/logout` incrementa la versión e invalida **todas** las sesiones de ese
profesional. Desactivar cuenta o establecimiento también impide uso de tokens ya
emitidos. Reasignar establecimiento invalida el token anterior. Cambiar contraseña
administrativamente debe incrementar `version_token` en la misma transacción.

Después de cinco contraseñas fallidas se bloquean nuevos logins por 15 minutos,
con contador persistido en PostgreSQL. Los errores no revelan si un correo existe.
La contraseña se verifica con un hash ficticio cuando la cuenta no existe. Las
respuestas de validación no reflejan entradas que puedan contener contraseñas.

## Rol secretaria (Clínica Odontológica)

Decisiones del equipo (23/10/2026): la secretaria **existe solo en la clínica
odontológica**, registra pacientes (puede anotar alergias, que son opcionales) y
gestiona la agenda. No tiene acceso clínico y **no puede archivar** historiales.
Sus permisos por defecto son `pacientes:leer`, `pacientes:registrar`, `citas:leer` y
`citas:gestionar`.

PostgreSQL lo impone para que ninguna herramienta lo salte:

- `006_rol_secretaria_citas.sql`: agrega el rol y los permisos `citas:*`, y triggers
  que impiden asignar permisos clínicos a una secretaria.
- `007_secretaria_restricciones.sql`: agrega `historiales:archivar` a los permisos
  vedados (`identidad.permisos_vedados_secretaria()`) y un `CHECK`
  (`ck_secretaria_solo_odontologia`) que exige `establecimiento = 'clinica_odontologica'`.
  Si alguna secretaria ya tenía `historiales:archivar`, la migración se lo quita.

`scripts.crear_profesional` rechaza antes de tocar la base una secretaria de otra
institución o con permisos vedados. En la API, las alergias del paciente se ocultan a
quien no tiene `historiales:leer`.

Para una base creada antes de estos cambios (PowerShell, desde la raíz, en este orden):

```powershell
Get-Content database\postgresql\006_rol_secretaria_citas.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
Get-Content database\postgresql\007_secretaria_restricciones.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
```

## Administración en dos niveles (migración 015)

Detalle y decisiones en [administracion_general.md](administracion_general.md).

- **Superusuario de plataforma**: la **única** cuenta sin establecimiento
  (`CHECK ((rol = 'superusuario') = (establecimiento IS NULL))`). Su token lleva
  `inst: null` y `/auth/me` devuelve `institucion: null`. Solo tiene
  `plataforma:administrar` y `pagos:ver`; los triggers impiden darle permisos clínicos y
  la API nunca abre un motor clínico con una cuenta sin institución. Un índice único
  (`ux_un_superusuario`) impide un segundo superusuario.
- **Administrador de cada entidad**: uno activo por entidad (`ux_un_admin_por_entidad`).
- **Baja definitiva lógica** (`eliminado_en`): una cuenta eliminada no inicia sesión (mismo
  error que una inactiva, sin revelar el motivo), sus tokens quedan revocados y el trigger
  `identidad.validar_reactivacion()` impide volver a habilitarla.

Crear el superusuario (pide la contraseña oculta; debe cambiarla en su primer ingreso):

```powershell
python -m scripts.crear_profesional --correo superusuario@example.com --nombres "Nombre" --apellidos "Apellido" --rol superusuario
```

**Si pierde el acceso** (contraseña olvidada o cuenta bloqueada) no hay superusuario de
respaldo: se recupera con la cuenta administrativa de PostgreSQL. El script pone una
contraseña nueva, quita el bloqueo, cierra sus sesiones, exige que elija otra al entrar y
deja la entrada en la bitácora:

```powershell
python -m scripts.crear_profesional --restablecer-superusuario
```

Para una base creada antes de este cambio, aplicar
`database/postgresql/015_administracion_dos_niveles.sql` (se detiene con un mensaje si
alguna entidad tiene más de un administrador activo).

## Crear la primera cuenta

Con las bases ejecutándose, desde PowerShell en la raíz:

```powershell
python -m scripts.crear_profesional --correo medico@example.com --nombres "Nombre" --apellidos "Apellido" --institucion centro_pediatrico --rol medico
```

La contraseña se pide oculta, dos veces. Se otorga solamente `pacientes:leer` por
defecto; usar `--permiso` repetido para permisos adicionales existentes. El alta es
atómica: un correo repetido o permiso desconocido revierte toda la operación.
Crear la cuenta también vincula el UUID al profesional local de la institución
(`personal_medico` en el Hospital General, `medico` en el Centro Pediátrico, colección
`profesionales` en el Laboratorio y la Clínica), sin copiar correo ni contraseña. Es
necesario para registrar consultas. Si el motor local no estaba disponible, la cuenta
central se conserva y se repite con `python -m scripts.sincronizar_profesionales`
(idempotente). La API responde 403 con ese mensaje si falta el vínculo.

En Swagger, ejecutar login, copiar `access_token` y pegarlo en **Authorize**. Después
probar `/auth/me` y la consulta de paciente. Una base vacía devuelve 404 para un ID
ausente; no significa que la conexión haya fallado.

Antes de publicar fuera del equipo: HTTPS y límite de peticiones por origen para
reducir intentos masivos a correos inexistentes; auditoría de accesos y un flujo de
recuperación/rectificación de cuentas. Esta entrega prepara el login local, no ese
despliegue. Firestore queda pendiente como almacenamiento clínico de odontología.
Se accederá desde el servidor con Firebase Admin SDK/IAM; no se necesita Firebase
Auth para la identidad central elegida. Consulta [la decisión de Firestore](decision_firestore.md)
para recordar que el SDK de servidor no queda restringido por Firestore Security
Rules: la API debe validar JWT y permisos centrales en cada operación.

La identidad transversal debe explicarse en la documentación de evaluación:
PostgreSQL administra acceso, pero no copia ni reemplaza los historiales de los
otros tres motores. Las operaciones clínicas comunes ya están completas en los
cuatro adaptadores.

Referencia: [FastAPI, hashing y JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
