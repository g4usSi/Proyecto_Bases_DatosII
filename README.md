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

El frontend incluye acceso, administración general, administración institucional y
pantallas de odontología y pediatría. Las operaciones clínicas de las otras instituciones están
disponibles en la API y en `/docs`.

## Requisitos

- Python 3.12.
- Docker Desktop iniciado, con contenedores Linux.
- Para odontología: clave de servicio de Firebase en `.secrets/firebase-adminsdk.json`.
  Sin ella, los otros motores y la administración funcionan; las operaciones clínicas
  de Firestore responden 503.

Ejecutar los comandos en **PowerShell, desde la raíz del proyecto**.

## Primera inicialización

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m scripts.configurar_desarrollo
docker compose --profile api up -d --build
docker compose logs -f api
```

El configurador completa `.env` sin reemplazar valores existentes. Docker inicializa las
bases vacías y crea las cuentas administrativas. `Ctrl+C` deja de seguir los logs sin
detener los contenedores.

| Dirección | Uso |
| --- | --- |
| <http://127.0.0.1:8000/app/> | Aplicación web |
| <http://127.0.0.1:8000/docs> | Documentación interactiva de la API |
| <http://127.0.0.1:8000/health/ready> | Conexión con los motores |

Puertos locales: API `8000`, PostgreSQL `5434`, MySQL `3307` y MongoDB `27018`.

## Cuentas de demostración

El usuario es el correo. Estas son las credenciales iniciales de las cuentas de demostración:

| Cuenta | Usuario | Contraseña inicial |
| --- | --- | --- |
| Superadmin | `superadmin@demo.local` | `DemoSalud2026!` |
| Hospital General | `admin.hospital@demo.local` | `DemoSalud2026!` |
| Centro Pediátrico | `admin.pediatria@demo.local` | `DemoSalud2026!` |
| Laboratorio Clínico | `admin.laboratorio@demo.local` | `DemoSalud2026!` |
| Clínica Odontológica | `admin.odontologia@demo.local` | `DemoSalud2026!` |

Se crean al inicializar PostgreSQL, aplicar la migración `017`, finalizar el comando de
migraciones y arrancar la API en desarrollo. Los accesos se imprimen en la consola de
Uvicorn o en `docker compose logs -f api`.

Si ya existe un administrador para ese alcance, se conservan su usuario, contraseña,
permisos y estado. No se duplican cuentas. Si la contraseña es distinta de la demo,
la consola indica `contrasena existente conservada`.

El superadmin administra la plataforma y cada administrador gestiona el personal de su
institución. Estas cuentas no tienen acceso clínico; desde la administración se crean
las cuentas de médicos, odontólogos y demás personal.

`HISTORIALES_CUENTAS_DEMO=false` desactiva la creación y la impresión al arrancar la API.
El initdb de Docker y la migración `017` crean las cuentas demo por separado.

## Iniciar y detener

```powershell
# Iniciar y reconstruir la API después de cambios.
docker compose --profile api up -d --build

# Revisar estado y consola.
docker compose ps
docker compose logs -f api

# Detener conservando los datos.
docker compose --profile api stop
```

Conservar `.env` y los volúmenes existentes para mantener las credenciales y los datos.
No usar `docker compose down -v` para actualizar: elimina las bases locales.

## Migraciones en bases existentes

Los scripts de inicialización solo se ejecutan automáticamente en volúmenes vacíos.
Aplicar **solo los archivos pendientes**, en orden. Ejemplo para verificar las cuentas demo:

```powershell
.\.venv\Scripts\python.exe -m scripts.aplicar_migracion database/postgresql/017_cuentas_demo.sql
```

El comando acepta varios archivos de `database/postgresql/`, `database/mysql/` o
`laboratorio_clinico_mongo.js` y asegura las cuentas demo al terminar el lote.
La identidad central debe estar actualizada hasta `015`. Algunas migraciones anteriores
no se pueden repetir: consultar la [guía de migraciones](documentacion-backend.md#14-cómo-aplicar-los-cambios-a-bases-ya-creadas).
Si se ejecuta SQL directamente, aplicar después `017` o reiniciar la API para asegurar
las cuentas.

## Desarrollo local

Para ejecutar la API con recarga automática y mantener las bases en Docker:

```powershell
docker compose --profile api stop api
docker compose up -d postgres mysql mongo
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Después de guardar la clave de Firebase, comprobarla y reiniciar la API:

```powershell
.\.venv\Scripts\python.exe -m scripts.probar_firestore
```

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check app scripts tests
.\.venv\Scripts\python.exe -m pip check
```

Para pruebas de integración de los tres motores locales, con Docker iniciado y
PostgreSQL/MySQL temporales:

```powershell
.\.venv\Scripts\python.exe -m scripts.probar_backend_temporal tests/integration --ignore=tests/integration/test_firestore.py
```

## Documentación

- [Backend, endpoints y migraciones](documentacion-backend.md).
- [Arquitectura](docs/arquitectura.md) y [administración](docs/administracion_general.md).
- [Frontend](docs/frontend.md) y [configuración de Firestore](docs/decision_firestore.md).
