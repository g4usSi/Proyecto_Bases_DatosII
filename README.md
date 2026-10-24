# Proyecto Bases de Datos II

Plataforma común de historiales clínicos con FastAPI, Python 3.12 y arquitectura
hexagonal. Identidad central en PostgreSQL: **un establecimiento por profesional**.
La API decide el motor después de autenticar; cada establecimiento conserva sus datos.

## Estado y continuidad

El trabajo permanece en `main`; las ramas de motor aún no se han creado.
Para retomar decisiones, pendientes, límites conocidos y pasos recomendados, leer
[contexto para el siguiente agente](docs/CONTEXTO_PARA_OTRO_AGENTE.md).

| Establecimiento | Motor | Estado actual |
| --- | --- | --- |
| Hospital General | PostgreSQL | SQL original integrado, identidad central y lectura de paciente. |
| Centro Pediátrico | MySQL 8.4 | Modelo revisado, reglas de integridad, stock y saldos; lectura de paciente. |
| Laboratorio Clínico | MongoDB 8 | Colecciones, validadores e índices; lectura de paciente. |
| Clínica Odontológica | Cloud Firestore | Completo: pacientes, consultas, archivo, citas, odontograma (estados fijos) y rol secretaria. [Modelo](docs/modelo_odontologia.md). |

No se han creado ramas nuevas. Las cinco operaciones del curso ya tienen rutas,
casos de uso y permisos; cada motor reemplaza sus piezas pendientes (HTTP 501).
Ver [operaciones comunes](docs/operaciones_comunes.md) y el [avance estimado](docs/avance.md).

**Frontend:** pendiente. Decisión: HTML/JS sencillo servido por la misma FastAPI (sin
React ni paso de compilación). Faltan los mockups; el plan, las pantallas por rol y el
odontograma interactivo están en [docs/frontend.md](docs/frontend.md).

### Decisiones del equipo vigentes

- Cada institución guarda solo sus propios pacientes (no se replican en los cuatro motores).
- `contacto` y `alergias` son campos **opcionales** al registrar un paciente.
- Rol `secretaria`: **solo en la clínica odontológica**. Registra pacientes (puede anotar
  alergias) y gestiona citas. No ve alergias, consultas, diagnósticos ni odontograma, y
  **no puede archivar** historiales. PostgreSQL lo impide con triggers y un `CHECK`.
- La clínica odontológica agenda citas y lleva odontograma con una **lista fija de
  estados** por pieza (12 valores, ver [docs/frontend.md](docs/frontend.md)).

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

## Conectar Firestore (Clínica Odontológica)

1. En Firebase: Configuración del proyecto > Cuentas de servicio > **Generar nueva
   clave privada**. Cada integrante puede generar la suya.
2. Guardarla como `.secrets\firebase-adminsdk.json` en esta raíz. `.secrets/` está
   ignorado por Git y por Docker: **no subir la clave**.
3. Instalar dependencias, completar `.env` y probar:

```powershell
python -m pip install -r requirements-dev.txt
python -m scripts.configurar_desarrollo
python -m scripts.probar_firestore
```

Debe responder `OK: escritura, lectura y borrado funcionan`. Al iniciar Uvicorn
aparece `Firestore conectado para la clinica odontologica`. Sin la clave, la API
arranca igual y solo la clínica odontológica responde 503.

Si la base de PostgreSQL ya existía antes del rol secretaria, aplicar **una vez, en
orden**, las migraciones 006 y 007 y luego copiar los perfiles de la clínica a Firestore.
Ambas son idempotentes, así que repetirlas no daña nada. Un volumen nuevo las ejecuta solo.

```powershell
Get-Content database\postgresql\006_rol_secretaria_citas.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
Get-Content database\postgresql\007_secretaria_restricciones.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
python -m scripts.sincronizar_profesionales
```

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
| `POST /api/v1/pacientes` | Registra paciente nuevo (`pacientes:registrar`). |
| `GET /api/v1/pacientes/{id}/historial` | Consultas paginadas (`historiales:leer`). |
| `POST /api/v1/pacientes/{id}/consultas` | Consulta + diagnósticos + tratamientos + recetas (`consultas:registrar`). |
| `POST /api/v1/pacientes/{id}/archivo` | Baja por traslado, fallecimiento o causa administrativa (`historiales:archivar`). |
| `POST /api/v1/citas`, `GET /api/v1/citas` | Agendar y ver agenda (`citas:gestionar`, `citas:leer`). |
| `POST /api/v1/citas/{id}/estado` | Atendida, cancelada (con motivo) o no asistió. |
| `GET/PUT /api/v1/pacientes/{id}/odontograma` | Odontograma FDI; el estado de la pieza debe estar en la lista fija, si no responde 422 (`historiales:leer` / `consultas:registrar`). |

401: credenciales/sesión inválidas; 403: permiso ausente; 404: paciente ausente;
409: historial archivado; 501: operación pendiente en ese motor; 503: motor no
disponible (por ejemplo, Firestore sin clave).

## Archivos y decisiones

- `laboratorio_clinico_mongo.js`: script solicitado de laboratorio, en esta raíz.
- `database/mysql/001_hospital_pediatrico.sql`: esquema revisado.
- `database/mysql/002_integridad.sql`: reglas, stock y consistencia de facturación.
- `database/mysql/original/`: copia intacta del SQL recibido.
- `database/postgresql/`: esquema del hospital, identidad y cuentas limitadas.
- [Revisión de MySQL](docs/revision_mysql.md), [modelo del laboratorio](docs/modelo_laboratorio.md).
- [Identidad central](docs/identidad_central.md), [arquitectura](docs/arquitectura.md),
  [trabajo por ramas](docs/ramas.md).
- [Decisión de Firebase/Firestore](docs/decision_firestore.md): conexión cloud,
  credenciales, IAM, costos y alternativa de emulador.
- [Guía de modelado de Firestore](docs/modelo_odontologia.md) y
  [operaciones comunes](docs/operaciones_comunes.md): qué falta en cada motor.
- [Plan del frontend](docs/frontend.md) y [avance estimado](docs/avance.md).

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

Firestore ya está completo. Pendiente: implementar en PostgreSQL, MySQL y MongoDB las
operaciones que hoy responden 501 (registro, historial, atención con
diagnósticos/tratamientos/recetas y archivo), hacer los mockups y el frontend
([plan](docs/frontend.md)) y redactar el documento comparativo.
Agregar auditoría y rectificaciones antes de permitir cambios clínicos. Para escrituras
coordinadas en varias colecciones, convertir MongoDB a replica set y probar transacciones.
Revisar también las reglas pendientes del esquema clínico original de PostgreSQL.

La entrega debe integrar los cuatro adaptadores en una sola aplicación. Las ramas
serán una forma de organizar desarrollo, no cuatro aplicaciones con contratos distintos.

La especificación del curso manda sobre las decisiones de implementación. Si cambia
el alcance, actualizar este README y el documento de continuidad juntos.

Referencias: [FastAPI, JWT y Argon2](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/),
[MySQL CHECK](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html),
[MongoDB schema validation](https://www.mongodb.com/docs/manual/core/schema-validation/).
