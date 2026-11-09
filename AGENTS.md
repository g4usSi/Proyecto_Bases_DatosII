# Guía para agentes: levantar el proyecto

Instrucciones para un agente de código (Claude Code, Codex, Copilot, etc.) que deba levantar y
verificar este proyecto en una máquina nueva. Para personas, la guía es el [README](README.md);
este archivo resume los mismos pasos en orden estricto, con lo que debe salir en cada uno.

## Reglas

- Trabajar siempre **desde la raíz del repositorio** (donde están `compose.yaml` y `README.md`).
- **Nunca** subir a Git `.env`, `.secrets/firebase-adminsdk.json` ni `entrega_configuracion.zip`.
  `.env` y `.secrets/*` ya están en `.gitignore`; no cambiar esas reglas.
- **No** imprimir en la conversación el contenido de `.env` ni de la clave de Firebase.
- **No** modificar `Dockerfile`, `compose.yaml`, migraciones (`database/`) ni código de `app/`
  para "hacer que arranque". El proyecto arranca tal cual; si algo falla, ver
  [Problemas conocidos](#problemas-conocidos) y avisar al usuario.
- **No** ejecutar `docker compose ... down -v` sin confirmación del usuario si las bases ya
  tenían datos: borra los volúmenes. En una máquina recién clonada no hay datos que perder.
- La aplicación usa datos de demostración; no cargar datos reales.

## Datos del proyecto

| Elemento | Valor |
| --- | --- |
| Lenguaje | Python **3.12** (FastAPI). Frontend estático servido por la API en `/app/`. |
| Bases | PostgreSQL 17, MySQL 8.4 y MongoDB 8 en Docker; Cloud Firestore en la nube. |
| Puertos (solo `127.0.0.1`) | API `8000`, PostgreSQL `5434`, MySQL `3307`, MongoDB `27018`. |
| Configuración | `.env` (lo genera `scripts.configurar_desarrollo` o viene en el zip de entrega). |
| Clave de Firestore | `.secrets/firebase-adminsdk.json` (no está en Git; se entrega aparte). |
| Python del entorno | Windows: `.\.venv\Scripts\python.exe` · Linux/macOS: `.venv/bin/python` |

En los comandos de abajo, `PY` es el Python del entorno según el sistema operativo.

## Pasos

### 0. Comprobar requisitos

```powershell
py -3.12 --version          # Linux/macOS: python3.12 --version  -> Python 3.12.x
docker version              # debe mostrar "Server"; si no, Docker Desktop no está iniciado
docker compose version
```

Si falta Python 3.12 o Docker, detenerse y pedir al usuario que lo instale o lo inicie.

### 1. Archivos de configuración

Si el usuario entregó `entrega_configuracion.zip`, extraerlo **en la raíz** del repositorio:

```powershell
Expand-Archive entrega_configuracion.zip -DestinationPath . -Force   # Linux/macOS: unzip -o entrega_configuracion.zip
```

Debe quedar `.env` en la raíz y `.secrets/firebase-adminsdk.json`. Si no hay zip, el paso 3
genera `.env`; sin la clave, la Clínica Odontológica responderá 503 (el resto funciona).
Preguntar al usuario por la clave antes de continuar sin ella.

### 2. Entorno de Python

```powershell
py -3.12 -m venv .venv                         # Linux/macOS: python3.12 -m venv .venv
PY -m pip install -r requirements-dev.txt
```

### 3. Completar `.env`

```powershell
PY -m scripts.configurar_desarrollo
```

Salida esperada: `Configuracion lista: N variables agregadas.` Con el `.env` del zip, `N` puede
ser 0: el script **nunca** reemplaza valores existentes. El aviso
`falta .secrets/firebase-adminsdk.json` solo aparece si no está la clave.

### 4. Levantar con Docker

```powershell
docker compose --profile api up -d --build
docker compose --profile api ps
```

La primera vez tarda de 1 a 3 minutos (descarga de imágenes e inicialización de bases).
Repetir `ps` hasta que `postgres`, `mysql`, `mongo` y `api` aparezcan como `(healthy)`.

### 5. Verificar

```powershell
curl.exe -s http://127.0.0.1:8000/health/ready     # Linux/macOS: curl -s ...
```

Resultado esperado (los cuatro en `ok`):

```json
{"status":"ok","instituciones":{"hospital_general":"ok","clinica_odontologica":"ok","laboratorio_clinico":"ok","centro_pediatrico":"ok"}}
```

Prueba de inicio de sesión (debe devolver un `access_token`):

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/auth/login -ContentType 'application/json' -Body '{"correo":"superadmin@demo.local","password":"DemoSalud2026!"}'
```

En Linux/macOS: `curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login -H 'Content-Type: application/json' -d '{"correo":"superadmin@demo.local","password":"DemoSalud2026!"}'`.

### 6. Cargar datos de demostración

Una sola vez (se pueden repetir sin duplicar):

```powershell
docker compose cp database/ejemplos/hospital_demo.sql postgres:/tmp/hospital_demo.sql
docker compose exec -T postgres psql -U historiales_admin -d hospital_general -v ON_ERROR_STOP=1 -q -f /tmp/hospital_demo.sql
PY -m scripts.cargar_catalogos laboratorio database/ejemplos/catalogo_laboratorio_demo.json
PY -m scripts.cargar_catalogos vacunas database/ejemplos/catalogo_vacunas_demo.json
```

Salidas esperadas: `Laboratorio: {'publicadas': ...}` y `Vacunas: {'tipos_nuevos': ...}`.

### 7. Pruebas (opcional)

```powershell
PY -m pytest                         # esperado: "... passed, ... skipped", 0 failed
PY -m ruff check .                   # esperado: "All checks passed!"
PY -m scripts.probar_backend_temporal tests/integration --ignore=tests/integration/test_firestore.py
```

La última usa bases temporales en los contenedores y las elimina al terminar.

### 8. Entregar al usuario

Informar: <http://127.0.0.1:8000/app/> (aplicación), <http://127.0.0.1:8000/docs> (API), el
resultado de `/health/ready` y las cuentas demo:

| Cuenta | Usuario | Contraseña |
| --- | --- | --- |
| Superadmin | `superadmin@demo.local` | `DemoSalud2026!` |
| Hospital General | `admin.hospital@demo.local` | `DemoSalud2026!` |
| Centro Pediátrico | `admin.pediatria@demo.local` | `DemoSalud2026!` |
| Laboratorio Clínico | `admin.laboratorio@demo.local` | `DemoSalud2026!` |
| Clínica Odontológica | `admin.odontologia@demo.local` | `DemoSalud2026!` |

Las cuentas de administración no tienen acceso clínico: el personal clínico se crea desde
**Usuarios y accesos** con el administrador de cada institución.

## Alternativa: API en consola

Con los pasos 0 a 3 hechos:

```powershell
docker compose --profile api stop api
docker compose up -d postgres mysql mongo
PY -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --log-config app/logging.json
```

Es un proceso que no termina: ejecutarlo en segundo plano o en otra terminal, y verificar
con el paso 5.

## Problemas conocidos

| Síntoma | Causa | Qué hacer |
| --- | --- | --- |
| `failed to connect to the docker API` / `dockerDesktopLinuxEngine` | Docker Desktop no está iniciado. | Pedir al usuario que lo abra; repetir el paso 4. |
| `Ejecuta python -m scripts.configurar_desarrollo` o `Falta ...PASSWORD` al levantar | `.env` incompleto o inexistente. | Paso 3. |
| `port is already allocated` | Puerto ocupado por otro programa. | Cambiar `API_PORT`, `POSTGRES_PORT`, `MYSQL_PORT` o `MONGO_PORT` en `.env` (y, para consola, los `HISTORIALES_*` correspondientes). |
| Contenedores `unhealthy` o la API no conecta tras cambiar `.env` | Volúmenes creados antes con otras contraseñas. | Con permiso del usuario: `docker compose --profile api down -v` y repetir el paso 4. |
| `clinica_odontologica: "no_configurada"` | Falta `.secrets/firebase-adminsdk.json`. | Colocar la clave y `docker compose --profile api restart api`. |
| `clinica_odontologica: "no_disponible"` | Sin salida a Internet hacia Google o reloj del sistema desfasado. | Revisar conexión y hora; `PY -m scripts.probar_firestore` muestra el detalle. |
| `CERTIFICATE_VERIFY_FAILED` en `pip install` durante el `--build` | Red con proxy que inspecciona TLS (redes corporativas o sandboxes). | No es un fallo del proyecto. Usar otra red o la alternativa en consola; no editar el `Dockerfile` del repositorio. |
| Las credenciales demo no funcionan | La base ya tenía cuentas con otras contraseñas. | `PY -m scripts.restablecer_cuentas_demo` con PostgreSQL iniciado. |
| La web dice «Tu área todavía no está en esta versión» | Imagen de la API antigua. | `docker compose --profile api up -d --build`. |

## Más contexto

- [README](README.md): guía completa para personas.
- [documentacion-backend.md](documentacion-backend.md): arquitectura, endpoints, permisos y migraciones.
- [.secrets/README.md](.secrets/README.md): manejo de la clave de Firebase.
