# Red de historiales clínicos

Proyecto de Bases de Datos II con FastAPI, Python 3.12 y frontend HTML/CSS/JavaScript.
La identidad del personal se centraliza en PostgreSQL; cada institución conserva sus
pacientes e historiales en su propio motor.

| Institución | Base de datos | Funciones principales |
| --- | --- | --- |
| Hospital General | PostgreSQL 17 | Consultas, citas, camas, ingresos y cobros. |
| Centro Pediátrico | MySQL 8.4 | Consultas, citas, tutores, crecimiento, vacunas y facturación. |
| Laboratorio Clínico | MongoDB 8 | Órdenes, muestras, resultados y validación. |
| Clínica Odontológica | Cloud Firestore | Consultas, citas, odontograma y funciones de secretaria. |

El frontend incluye acceso, administración general, administración institucional y las
pantallas clínicas de las cuatro instituciones: odontología, pediatría, hospital y laboratorio.

## Requisitos

- **Python 3.12** (`py -3.12 --version` en Windows, `python3.12 --version` en Linux/macOS).
- **Docker Desktop** iniciado, con contenedores Linux (incluye `docker compose`).
- Puertos libres en `127.0.0.1`: `8000` (API), `5434` (PostgreSQL), `3307` (MySQL) y
  `27018` (MongoDB). Se cambian en `.env` si están ocupados.
- **Clave de Firebase** para la Clínica Odontológica: no está en Git. Se entrega por
  separado y se coloca en `.secrets/firebase-adminsdk.json` (ver
  [`.secrets/README.md`](.secrets/README.md)). Sin ella todo lo demás funciona y solo las
  operaciones de odontología responden 503.

Los comandos están escritos para **PowerShell, desde la raíz del proyecto**. En Linux o
macOS se usa `.venv/bin/python` en lugar de `.\.venv\Scripts\python.exe`.

## Revisión rápida (de cero, con Docker)

```powershell
# 1. Entorno de Python y herramientas
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 2. Configuración: crea .env con contraseñas aleatorias (no sobrescribe valores existentes)
.\.venv\Scripts\python.exe -m scripts.configurar_desarrollo

# 3. Clave de Firebase (recibida aparte)
Copy-Item <ruta-de-la-clave>.json .secrets\firebase-adminsdk.json

# 4. Levantar PostgreSQL, MySQL, MongoDB y la API
docker compose --profile api up -d --build
docker compose --profile api ps

# 5. Cargar los datos de demostración (una sola vez; se puede repetir sin duplicar)
docker compose cp database/ejemplos/hospital_demo.sql postgres:/tmp/hospital_demo.sql
docker compose exec postgres psql -U historiales_admin -d hospital_general -f /tmp/hospital_demo.sql
.\.venv\Scripts\python.exe -m scripts.cargar_catalogos laboratorio database/ejemplos/catalogo_laboratorio_demo.json
.\.venv\Scripts\python.exe -m scripts.cargar_catalogos vacunas database/ejemplos/catalogo_vacunas_demo.json
```

La primera vez Docker descarga las imágenes e inicializa las bases (1 a 3 minutos). Cuando
`docker compose --profile api ps` muestra los cuatro servicios como `healthy`, abrir:

| Dirección | Uso |
| --- | --- |
| <http://127.0.0.1:8000/app/> | Aplicación web |
| <http://127.0.0.1:8000/docs> | Documentación interactiva de la API |
| <http://127.0.0.1:8000/health/ready> | Estado de los cuatro motores (todos deben decir `ok`) |

Si `clinica_odontologica` aparece como `no_configurada`, falta la clave del paso 3: copiarla
y ejecutar `docker compose --profile api restart api`.

En lugar del paso 2 también se puede copiar la plantilla y completarla con el mismo comando
(rellena solo los valores vacíos):

```powershell
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m scripts.configurar_desarrollo
```

## Cuentas de demostración

El usuario es el correo. Se crean solas al inicializar la base y arrancar la API:

| Cuenta | Usuario | Contraseña inicial |
| --- | --- | --- |
| Superadmin | `superadmin@demo.local` | `DemoSalud2026!` |
| Hospital General | `admin.hospital@demo.local` | `DemoSalud2026!` |
| Centro Pediátrico | `admin.pediatria@demo.local` | `DemoSalud2026!` |
| Laboratorio Clínico | `admin.laboratorio@demo.local` | `DemoSalud2026!` |
| Clínica Odontológica | `admin.odontologia@demo.local` | `DemoSalud2026!` |

Los accesos también se imprimen en `docker compose --profile api logs api`.

El superadmin administra la plataforma y cada administrador gestiona el personal de su
institución. Estas cuentas **no tienen acceso clínico**: para probar las pantallas clínicas,
entrar con el administrador de cada institución y crear el personal en
**Usuarios y accesos** (por ejemplo, un médico en el Hospital General, un laboratorista y un
médico que solicita órdenes en el Laboratorio, un odontólogo o secretaria en la Clínica).
Cada cuenta nueva cambia su contraseña al primer ingreso.

Si ya existe un administrador para ese alcance, se conservan su usuario, contraseña,
permisos y estado; no se duplican cuentas. Si las credenciales de la tabla no funcionan
porque la base ya tenía cuentas, ejecutar una vez, con PostgreSQL iniciado:

```powershell
.\.venv\Scripts\python.exe -m scripts.restablecer_cuentas_demo
```

Deja los cinco correos y contraseñas como en la tabla, conserva sus datos, desbloquea el
acceso y cierra las sesiones anteriores. `HISTORIALES_CUENTAS_DEMO=false` en `.env` desactiva
la creación de cuentas al arrancar la API.

## Datos de demostración

Las bases se inicializan vacías. El paso 5 de la revisión rápida carga:

- **Hospital General**: áreas, habitaciones, camas, servicios y tarifas (`hospital_demo.sql`).
- **Laboratorio Clínico**: catálogo de pruebas con rangos de referencia.
- **Centro Pediátrico**: catálogo de vacunas de partida (basado en el esquema nacional de
  Guatemala). El administrador del centro puede ampliarlo en **Catálogo de vacunas**.

Son datos de demostración, no de uso clínico.

## Levantar en consola (API con Uvicorn)

Útil para desarrollo: la API corre en la terminal con recarga automática y las bases
siguen en Docker. Requiere haber hecho los pasos 1 a 3 de la revisión rápida.

```powershell
# Si la API de Docker está corriendo, detenerla para liberar el puerto 8000
docker compose --profile api stop api

# Solo las bases de datos
docker compose up -d postgres mysql mongo

# API en consola
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --log-config app/logging.json
```

La terminal muestra el enlace directo a <http://127.0.0.1:8000/app/>. `Ctrl+C` la detiene.
En este modo la API lee `.env` directamente (las direcciones `127.0.0.1` y los puertos
`5434`, `3307` y `27018`). Para comprobar la clave de Firebase:

```powershell
.\.venv\Scripts\python.exe -m scripts.probar_firestore
```

## Iniciar, detener y actualizar (Docker)

```powershell
# Iniciar (reconstruye la API si cambió el código)
docker compose --profile api up -d --build

# Estado y consola
docker compose --profile api ps
docker compose --profile api logs -f api      # Ctrl+C deja de seguir los logs

# Detener conservando los datos
docker compose --profile api stop

# Borrar TODO (contenedores y bases) para empezar de cero
docker compose --profile api down -v
```

> [!WARNING]
> Después de `git pull` o de cambiar de rama, usar siempre `--build`: la imagen contiene una
> copia de `app/`, incluido el frontend. Sin `--build`, Compose puede reutilizar una imagen
> anterior y mostrar «Tu área todavía no está en esta versión».

`down -v` elimina las bases locales; para actualizar no hace falta. Si se borra o cambia
`.env` con bases ya creadas, las contraseñas nuevas no coincidirán con las guardadas en los
volúmenes: conservar `.env` o empezar de cero con `down -v`.

Si aparece un error de conexión a `dockerDesktopLinuxEngine`, abrir Docker Desktop, esperar
a que el motor esté listo y repetir el comando. Si se mueve la carpeta del proyecto, recrear
los contenedores (los datos se conservan):

```powershell
docker compose --profile api up -d --build --force-recreate
```

## Configuración y secretos

| Archivo | En Git | Contenido |
| --- | --- | --- |
| `.env.example` | Sí | Plantilla con todas las variables, sin valores secretos. |
| `.env` | No | Contraseñas y DSN locales. Lo genera `scripts.configurar_desarrollo`. |
| `.secrets/README.md` | Sí | Instrucciones para la clave de Firebase. |
| `.secrets/firebase-adminsdk.json` | No | Clave de cuenta de servicio de Firebase (se entrega aparte). |

Docker monta `.secrets/` en la API como solo lectura; la clave nunca se copia a la imagen.
La descripción de cada variable está en `.env.example` y en la
[documentación del backend](documentacion-backend.md#10-configuración-variables-historiales_).

## Migraciones en bases existentes

Los scripts de inicialización solo se ejecutan automáticamente en volúmenes vacíos (como en
una revisión de cero). En bases ya creadas, aplicar **solo los archivos pendientes**, en orden:

```powershell
.\.venv\Scripts\python.exe -m scripts.aplicar_migracion database/postgresql/017_cuentas_demo.sql
```

El comando acepta varios archivos de `database/postgresql/`, `database/mysql/` o
`laboratorio_clinico_mongo.js` y asegura las cuentas demo al terminar. Algunas migraciones
anteriores no se pueden repetir: ver la
[guía de migraciones](documentacion-backend.md#14-cómo-aplicar-los-cambios-a-bases-ya-creadas).

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check app scripts tests
.\.venv\Scripts\python.exe -m pip check
```

Pruebas de integración contra PostgreSQL, MySQL y MongoDB reales (con Docker iniciado; crea
bases temporales y las elimina al terminar):

```powershell
.\.venv\Scripts\python.exe -m scripts.probar_backend_temporal tests/integration --ignore=tests/integration/test_firestore.py
```

## Documentación

- [Backend, endpoints y migraciones](documentacion-backend.md).
- [Arquitectura](docs/arquitectura.md) y [administración](docs/administracion_general.md).
- [Frontend](docs/frontend.md) y [configuración de Firestore](docs/decision_firestore.md).
