# Proyecto Bases de Datos II

## Arrancar la aplicación

Ejecutar en PowerShell, desde esta carpeta, con Docker Desktop abierto.

### Arranque normal

```powershell
docker compose --profile api up -d --build
```

Abrir <http://127.0.0.1:8000/docs>. Para detener sin borrar datos:

```powershell
docker compose --profile api stop
```

### Primera vez

Requiere Python 3.12 o 3.13 y Docker Desktop.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m scripts.configurar_desarrollo
docker compose --profile api up -d --build
```

Después, crear la primera cuenta. El comando pide una contraseña de al menos 12 caracteres:

```powershell
.\.venv\Scripts\python.exe -m scripts.crear_profesional --correo odontologo@example.com --nombres "Nombre" --apellidos "Apellido" --institucion clinica_odontologica --rol odontologo
```

La Clínica Odontológica necesita además la clave de Firebase en
`.secrets\firebase-adminsdk.json` ([cómo obtenerla](#conectar-firestore-clínica-odontológica)).
Sin ella, las otras tres instituciones funcionan y la clínica responde 503.

### Comprobar que todo responde

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health/ready | ConvertTo-Json
```

Cada institución debe aparecer como `ok`. En el primer arranque, MySQL puede tardar unos
segundos más en aceptar conexiones: si `centro_pediatrico` sale `no_disponible`, repetir el
comando.

| Dirección | Contenido |
| --- | --- |
| <http://127.0.0.1:8000/docs> | Documentación interactiva de la API |
| <http://127.0.0.1:8000/health> | Salud del proceso |
| <http://127.0.0.1:8000/health/ready> | Conexión con los cuatro motores |

### Si tus bases se crearon antes de las últimas migraciones

Los scripts de `database/` solo se ejecutan solos cuando el volumen está vacío. Si la API
falla con tablas inexistentes, por ejemplo en citas, aplicar esto **una sola vez**, después
del arranque normal. Conserva los datos. Las migraciones de MySQL no se deben repetir.

```powershell
docker compose exec -T postgres sh -c 'for f in /docker-entrypoint-initdb.d/009_*.sql /docker-entrypoint-initdb.d/01[0-4]_*.sql; do psql -q -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general -f $f || exit 1; done'
docker compose exec -T mysql sh -c 'for f in /docker-entrypoint-initdb.d/00[6-9]_*.sql /docker-entrypoint-initdb.d/01[0-4]_*.sql; do MYSQL_PWD=$MYSQL_ROOT_PASSWORD mysql -uroot --default-character-set=utf8mb4 hospital_pediatrico < $f || exit 1; done'
docker compose exec -T mongo sh -c 'mongosh --quiet -u historiales_admin -p $MONGO_INITDB_ROOT_PASSWORD --authenticationDatabase admin /docker-entrypoint-initdb.d/001_laboratorio.js'
.\.venv\Scripts\python.exe -m scripts.sincronizar_profesionales
```

Estos rangos corresponden a un volumen creado con PostgreSQL hasta `008` y MySQL hasta
`005`. Si tu base es de otra época, consultar la
[sección 14 de la documentación](documentacion-backend.md#14-cómo-aplicar-los-cambios-a-bases-ya-creadas).

### Desarrollar con recarga automática

Las bases corren en Docker y la API en tu máquina, así los cambios en el código se aplican
sin reconstruir la imagen:

```powershell
docker compose --profile api stop api
docker compose up -d postgres mysql mongo
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Avisos

- **Conservar `.env`:** sus contraseñas son las de los volúmenes ya creados y no está en
  Git. `configurar_desarrollo` solo agrega lo que falta. No copiar `.env.example` encima.
- **Evitar `docker compose down -v`:** borra todas las bases locales.
- **Usar `--build` después de cambiar de rama o actualizar el código:** sin él, Docker sigue
  usando la API anterior.

## Qué es

Plataforma común de historiales clínicos con FastAPI y arquitectura hexagonal. La identidad
del personal está centralizada en PostgreSQL: **cada profesional pertenece a un
establecimiento**. La API decide el motor después de autenticar y cada establecimiento
conserva sus propios datos.

| Establecimiento | Motor | Estado actual |
| --- | --- | --- |
| Hospital General | PostgreSQL 17 | Operaciones clínicas, citas, camas, ingresos de emergencia, órdenes médicas, alta y cobros. |
| Centro Pediátrico | MySQL 8.4 | Operaciones clínicas, citas, crecimiento, vacunación sin control de stock, tutores y facturación. |
| Laboratorio Clínico | MongoDB 8 | Operaciones clínicas, citas, catálogo versionado, órdenes, muestras, resultados y validación. |
| Clínica Odontológica | Cloud Firestore | Operaciones clínicas, citas, odontograma y rol de secretaria. Cubre las pantallas clínicas del mockup ([contrato](docs/contrato_clinica_odontologica.md)). |

Las cinco operaciones del curso, la búsqueda por nombre, las adendas, la corrección de datos
y alergias, las citas sin solapes, la administración de profesionales y el cambio de
contraseña funcionan en los cuatro motores. Los módulos propios de un establecimiento
responden 501 en los demás.

## Estado

- **Backend:** funcional. Referencia completa de rutas, permisos y motores en
  [documentacion-backend.md](documentacion-backend.md).
- **Frontend:** sin construir. El [mockup](docs/referencia/Historiales%20identidad%20visual.html)
  está listo y el cliente será HTML/JS servido por la misma FastAPI ([plan](docs/frontend.md)).
- **Documento comparativo:** pendiente de redactar ([avance](docs/avance.md)).
- **Ramas:** el desarrollo se reparte por establecimiento. Este README describe la rama
  `Clinica-Odontologica`. Las rutas `/profesionales/resumen` y `/profesionales/bitacora`
  están en la rama del Centro Pediátrico y todavía no llegan aquí.

Para retomar el trabajo, leer el [contexto para el siguiente agente](docs/CONTEXTO_PARA_OTRO_AGENTE.md).

### Decisiones del equipo vigentes

- Cada institución guarda solo sus propios pacientes (no se replican en los cuatro motores).
- Solo la identidad del personal es central; un mismo paciente se registra por separado en
  cada establecimiento al que acuda (expedientes independientes).
- Las citas del Laboratorio Clínico son una función extra: existen en el backend, pero no
  se priorizan en el frontend. El Centro Pediátrico no controla stock por lote de vacunas.
  Detalle en [documentacion-backend.md](documentacion-backend.md#0-decisiones-de-diseño-vigentes).
- `contacto` y `alergias` son campos **opcionales** al registrar un paciente.
- Rol `secretaria`: **solo en la clínica odontológica**. Registra pacientes (puede anotar
  alergias) y gestiona citas. No ve alergias, consultas, diagnósticos ni odontograma, y
  **no puede archivar** historiales. PostgreSQL lo impide con triggers y un `CHECK`.
- La clínica odontológica lleva el odontograma con una **lista fija de 12 estados** por
  pieza ([contrato](docs/contrato_clinica_odontologica.md#valores-y-límites)).

## Conectar Firestore (Clínica Odontológica)

1. En Firebase: Configuración del proyecto > Cuentas de servicio > **Generar nueva
   clave privada**. Cada integrante puede generar la suya.
2. Guardarla como `.secrets\firebase-adminsdk.json` en esta raíz. `.secrets/` está
   ignorado por Git y por Docker: **no subir la clave**.
3. Probar la conexión. La prueba escribe, lee y borra un documento en el proyecto real:

```powershell
.\.venv\Scripts\python.exe -m scripts.probar_firestore
```

Debe responder `OK: escritura, lectura y borrado funcionan`. Al iniciar la API aparece
`Firestore conectado para la clinica odontologica`. Si la API ya estaba en marcha, reiniciarla
con `docker compose --profile api restart api` para que cargue la clave.

## Cuentas y login

No hay autorregistro ni cuentas de ejemplo: cada cuenta se crea con `crear_profesional`.

- **Instituciones:** `hospital_general`, `centro_pediatrico`, `laboratorio_clinico`,
  `clinica_odontologica`.
- **Roles:** `medico`, `enfermeria`, `laboratorista`, `odontologo`, `secretaria`,
  `administrador`.
- **Permisos por defecto:** `odontologo`, `secretaria`, `laboratorista` y `administrador`
  reciben los de su rol. `medico` y `enfermeria` solo reciben `pacientes:leer`, así que
  hay que indicar los demás con `--permiso`:

```powershell
.\.venv\Scripts\python.exe -m scripts.crear_profesional --correo medico@example.com --nombres "Nombre" --apellidos "Apellido" --institucion centro_pediatrico --rol medico --permiso pacientes:leer --permiso pacientes:registrar --permiso historiales:leer --permiso consultas:registrar
```

Al crear la cuenta también se vincula al profesional local de su institución, lo que es
necesario para registrar consultas. Si ese motor no estaba disponible, repetir el vínculo con
`python -m scripts.sincronizar_profesionales`.

Para probar en `/docs`: ejecutar `POST /api/v1/auth/login` con correo y contraseña, copiar
el `access_token`, pegarlo en **Authorize** y llamar a `GET /api/v1/auth/me`.

Para cargar los catálogos de vacunas y pruebas de laboratorio (datos DEMO):

```powershell
.\.venv\Scripts\python.exe -m scripts.cargar_catalogos vacunas database/ejemplos/catalogo_vacunas_demo.json
.\.venv\Scripts\python.exe -m scripts.cargar_catalogos laboratorio database/ejemplos/catalogo_laboratorio_demo.json
```

## Rutas principales

Prefijo `/api/v1`, salvo las de salud. La lista completa está en `/docs` y en la
[documentación del backend](documentacion-backend.md#3-endpoints).

| Ruta | Función | Disponible en |
| --- | --- | --- |
| `GET /health`, `GET /health/ready` | Salud del proceso y conexión con los motores. | Todos |
| `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | Sesión con JWT de 30 minutos, cierre y datos del usuario. | Todos |
| `POST /auth/cambiar-contrasena` | Cambia la contraseña y devuelve un token nuevo. | Todos |
| `GET/POST /pacientes`, `GET/PATCH /pacientes/{id}` | Buscar, registrar, leer y corregir pacientes. | Todos |
| `POST /pacientes/{id}/alergias` | Agregar alergias. | Todos |
| `GET /pacientes/{id}/historial` | Consultas paginadas. | Todos |
| `POST /pacientes/{id}/consultas`, `POST .../consultas/{id}/adenda` | Consulta con diagnósticos, tratamientos y recetas, y sus adendas. | Todos |
| `POST /pacientes/{id}/archivo` | Baja por traslado, fallecimiento o causa administrativa. | Todos |
| `GET/POST /citas`, `POST /citas/{id}/estado`, `GET /citas/profesionales` | Agenda, cambio de estado y profesionales que atienden. | Todos |
| `/profesionales` | Administración del personal de la institución. | Todos |
| `GET /pacientes/{id}/odontograma`, `PUT .../odontograma/piezas/{pieza}` | Odontograma FDI. | Clínica Odontológica |
| `/pacientes/{id}/crecimiento`, `/pacientes/{id}/vacunacion`, `/vacunas` | Crecimiento y vacunación. | Centro Pediátrico |
| `/pacientes/{id}/tutores`, `/tutores` | Tutores del paciente. | Centro Pediátrico |
| `/laboratorio/ordenes`, `/laboratorio/pruebas`, `/pacientes/{id}/ordenes` | Tablero, catálogo, órdenes, muestras, resultados y validación. | Laboratorio Clínico |
| `/camas`, `/ingresos`, `/hospital/resumen`, `/departamentos` | Camas, emergencias, ingresos y resumen. | Hospital General |
| `/cobros`, `/servicios`, `/pacientes/{id}/cobros` | Cobros y pagos. | Hospital General y Centro Pediátrico |

| Código | Significado |
| --- | --- |
| 401 | Credenciales o sesión inválidas. |
| 403 | Falta el permiso. |
| 404 | Paciente, consulta o cita inexistente. |
| 409 | Conflicto: historial archivado, horario ocupado o estado final. |
| 422 | Dato inválido. |
| 501 | El módulo no existe en el motor de esa institución. |
| 503 | Motor no disponible, por ejemplo Firestore sin clave. |

## Docker

Puertos locales por defecto, todos publicados solo en `127.0.0.1`:

| Servicio | Puerto |
| --- | --- |
| API | 8000 |
| PostgreSQL | 5434 |
| MySQL | 3307 |
| MongoDB | 27018 |

Los volúmenes conservan los datos al detener los contenedores. Las imágenes no incluyen
`.env`, credenciales administrativas ni PDFs del proyecto. Editar un script de `database/`
no modifica un volumen ya inicializado: hay que aplicarlo como migración.

## Archivos y documentación

- `laboratorio_clinico_mongo.js`: colecciones, validadores e índices del laboratorio.
- `database/postgresql/`: hospital, identidad y permisos (`001`–`014`).
- `database/mysql/`: centro pediátrico y permisos (`001`–`014`). `original/` guarda intacto
  el SQL recibido y `010` retira el stock por lote.
- `database/ejemplos/` y `scripts/cargar_catalogos.py`: catálogos con datos DEMO.
- [Documentación del backend](documentacion-backend.md),
  [arquitectura](docs/arquitectura.md) e [identidad central](docs/identidad_central.md).
- [Contrato de la clínica con el frontend](docs/contrato_clinica_odontologica.md),
  [modelo de Firestore](docs/modelo_odontologia.md) y
  [decisión de Firestore](docs/decision_firestore.md).
- [Revisión de MySQL](docs/revision_mysql.md), [modelo del laboratorio](docs/modelo_laboratorio.md),
  [operaciones comunes](docs/operaciones_comunes.md) y
  [administración general](docs/administracion_general.md).
- [Plan del frontend](docs/frontend.md), [avance estimado](docs/avance.md) y
  [trabajo por ramas](docs/ramas.md).

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pip check
```

Las pruebas habituales usan dobles y no necesitan bases de datos. Las pruebas reales se
activan explícitamente, con los contenedores en marcha:

```powershell
$env:HISTORIALES_TEST_INTEGRATION = '1'
.\.venv\Scripts\python.exe -m pytest
Remove-Item Env:HISTORIALES_TEST_INTEGRATION
```

Estas pruebas insertan registros sintéticos en las bases configuradas en `.env`, incluido
el proyecto de Firestore si existe la clave, y los eliminan al terminar. MySQL usa una base
temporal. No usarlas con datos reales sin configurar un entorno de pruebas separado.

## Trabajo siguiente

- Construir el frontend a partir del [mockup](docs/referencia/Historiales%20identidad%20visual.html).
- Redactar el documento comparativo ([qué falta](docs/avance.md#documento-comparativo-pendiente-de-redactar)).
- Integrar las ramas en una sola aplicación para la entrega: dos usuarios de instituciones
  distintas deben poder operar a la vez, cada uno sobre su motor.
- Opcional: convertir MongoDB a *replica set* para usar transacciones y cerrar la ventana de
  milisegundos entre una consulta y una baja simultáneas
  ([operaciones comunes](docs/operaciones_comunes.md)).

La especificación del curso manda sobre las decisiones de implementación. Si cambia el
alcance, actualizar este README y el documento de continuidad juntos.
