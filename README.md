# Proyecto Bases de Datos II

Plataforma común de historiales clínicos con FastAPI, Python 3.12 y arquitectura
hexagonal. Identidad central en PostgreSQL: **un establecimiento por profesional**.
La API decide el motor después de autenticar; cada establecimiento conserva sus datos.

| Establecimiento | Motor | Estado actual |
| --- | --- | --- |
| Hospital General | PostgreSQL | SQL original integrado, identidad central y lectura de paciente. |
| Centro Pediátrico | MySQL 8.4 | Modelo revisado, reglas de integridad, stock y saldos; lectura de paciente. |
| Laboratorio Clínico | MongoDB 8 | Colecciones, validadores e índices; lectura de paciente. |
| Clínica Odontológica | Cloud Firestore | Pendiente. |

No se han creado ramas nuevas. La interfaz web y el CRUD clínico completo siguen
pendientes; esta base ya permite login real y lectura autorizada en tres motores.

## Arranque local en PowerShell

Desde esta raíz, donde están `app`, `compose.yaml` y `.venv`:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m scripts.configurar_desarrollo
docker compose up -d postgres mysql mongo
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

El generador agrega valores faltantes y secretos aleatorios a `.env`; conserva la
configuración existente. No copiar `.env.example` sobre un `.env` ya configurado.
Para ejecutar sin activar el entorno, reemplazar `python` por
`.\.venv\Scripts\python.exe`. Usar `python -m pip` evita launchers del entorno
virtual que todavía apunten a la carpeta anterior.

- API: <http://127.0.0.1:8000/>
- Documentación interactiva: <http://127.0.0.1:8000/docs>
- Salud del proceso: <http://127.0.0.1:8000/health>

Si Docker ya ejecuta la API en 8000, primero usar `docker compose stop api`, o
arrancar Uvicorn con `--port 8001`. Los tres motores pueden seguir ejecutándose.
El perfil `api` evita que iniciar solamente las bases ocupe el puerto de Uvicorn.

## Ejecutar todo en Docker

```powershell
python -m scripts.configurar_desarrollo
docker compose --profile api up -d --build
docker compose ps
```

Puertos locales por defecto: PostgreSQL 5434, MySQL 3307, MongoDB 27018 y API 8000.
Todos se publican en 127.0.0.1. Los volúmenes conservan datos al detener contenedores.
Las imágenes no incluyen `.env`, credenciales administrativas ni PDFs del proyecto.
Los SQL/JS de inicialización se montan aparte y se ejecutan al crear un volumen vacío.
Editar un SQL no modifica automáticamente un volumen ya inicializado: aplicar una
migración o parche explícito conservando datos; no usar `down -v` como rutina.

## Primera cuenta y login

```powershell
python -m scripts.crear_profesional --correo medico@example.com --nombres "Nombre" --apellidos "Apellido" --institucion centro_pediatrico --rol medico
```

Se solicita la contraseña oculta; no se publica una cuenta con contraseña de ejemplo.
En `/docs`, ejecutar `POST /api/v1/auth/login` con correo y contraseña. Copiar el
`access_token`, pegarlo en **Authorize** y probar `/auth/me`. El establecimiento se
obtiene de PostgreSQL. Una base sin pacientes responderá 404 al consultar un ID.

| Ruta | Función |
| --- | --- |
| `GET /health` | Salud del proceso, sin comprobar conexiones. |
| `POST /api/v1/auth/login` | Credenciales centrales, JWT de 30 minutos. |
| `GET /api/v1/auth/me` | Usuario, institución y permisos vigentes. |
| `POST /api/v1/auth/logout` | Revoca todas las sesiones del profesional. |
| `GET /api/v1/pacientes/{id_paciente}` | Lee en el motor de la institución autorizada. |

401: credenciales/sesión inválidas; 403: permiso ausente; 404: paciente ausente;
503: motor o integración no disponible. Firestore devuelve 503 hasta conectarlo.
La API todavía no publica operaciones de escritura de expedientes.

## Archivos y decisiones

- `laboratorio_clinico_mongo.js`: script solicitado de laboratorio, en esta raíz.
- `database/mysql/001_hospital_pediatrico.sql`: esquema revisado.
- `database/mysql/002_integridad.sql`: reglas, stock y consistencia de facturación.
- `database/mysql/original/`: copia intacta del SQL recibido.
- `database/postgresql/`: esquema del hospital, identidad y cuentas limitadas.
- [Revisión de MySQL](docs/revision_mysql.md), [modelo del laboratorio](docs/modelo_laboratorio.md).
- [Identidad central](docs/identidad_central.md), [arquitectura](docs/arquitectura.md),
  [trabajo por ramas](docs/ramas.md).

## Verificación

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

Las pruebas habituales usan dobles para aislar reglas y autorización. Las pruebas
reales se activan explícitamente, con los tres contenedores ejecutándose:

```powershell
$env:HISTORIALES_TEST_INTEGRATION = '1'
python -m pytest
Remove-Item Env:HISTORIALES_TEST_INTEGRATION
```

MySQL se prueba en una base temporal creada y eliminada por la suite. Las pruebas
de PostgreSQL/MongoDB y enrutamiento insertan registros sintéticos identificados y
los eliminan al terminar. Verifican permisos vigentes, bloqueos de login, aislamiento
institucional, alergias múltiples, archivo, control del paciente correcto, stock,
validación documental y dos pagos simultáneos. No usar estas pruebas con datos reales
sin configurar un entorno de pruebas separado.

## Trabajo siguiente

Completar Firestore y definir/implementar las operaciones comunes de registro,
consulta de historial, atención con diagnósticos/tratamientos/recetas y archivo.
Agregar auditoría y rectificaciones antes de permitir cambios clínicos. Para escrituras
coordinadas en varias colecciones, convertir MongoDB a replica set y probar transacciones.
Revisar también las reglas pendientes del esquema clínico original de PostgreSQL.

La entrega debe integrar los cuatro adaptadores en una sola aplicación. Las ramas
serán una forma de organizar desarrollo, no cuatro aplicaciones con contratos distintos.

Referencias: [FastAPI, JWT y Argon2](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/),
[MySQL CHECK](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html),
[MongoDB schema validation](https://www.mongodb.com/docs/manual/core/schema-validation/).
