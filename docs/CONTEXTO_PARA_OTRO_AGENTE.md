# Relevo del proyecto para otro agente

## Actualización 3 de noviembre de 2026 — Integración en `Develop`

- Segunda integración: incorporados los commits de Henry hasta `f0c1ee4` desde
  `Backend/hospital-pediatrico`. El frontend carga pediatría y odontología junto con
  administración; se combinaron imports, estilos, iconos, formatos y pruebas comunes.
- `python -m scripts.restablecer_cuentas_demo` recupera explícitamente los cinco accesos
  del README en bases existentes, conservando IDs/permisos/datos y revocando sesiones.
  El arranque normal sigue sin sobrescribir credenciales. En esta instalación se recuperó
  el superadmin antiguo y se aplicaron las migraciones MySQL 004–014 que faltaban.
- Verificación de esta actualización: 186 pruebas habituales, 6 de cuentas demo sobre
  PostgreSQL temporal, 37 módulos JavaScript válidos, cinco logins HTTP y acceso web del
  superadmin sin errores de consola. El resumen ya incluye los tres motores locales;
  Firestore continúa sin clave de servicio en esta máquina.
- Integradas las cuatro ramas de entidades mediante commits de merge. Los conflictos de
  documentación se resolvieron conservando facturación pediátrica y cambios odontológicos.
- La administración de `Develop` conserva sus dos niveles y permisos originales.
- `017_cuentas_demo.sql` crea el superadmin y los cuatro administradores faltantes;
  se ejecuta en initdb, al arrancar la API de desarrollo y al finalizar
  `python -m scripts.aplicar_migracion <archivos pendientes>`. No sobrescribe cuentas.
- Los cinco usuarios y su contraseña inicial (`DemoSalud2026!`) están en el README y
  se imprimen al arrancar. Si una cuenta tiene otra contraseña, se informa que se conserva.
- La imagen incluye el seed y los JavaScript del frontend, antes excluidos por `.dockerignore`.
- Se serializan las reservas de citas por profesional antes de evaluar la exclusion GiST:
  corrige un deadlock detectado al probar dos reservas simultaneas; sigue devolviendo conflicto.
- Verificado: 184 pruebas habituales; 179 pruebas de integracion local entre la corrida general
  y la repeticion de las 43 de enrutamiento/PostgreSQL tras corregir dos fallos. Una prueba
  de Firestore dentro de administracion se omitio por falta de clave; su suite cloud no se ejecuto.
  Docker initdb desde cero creo las cinco cuentas y la imagen permitio sus cinco logins.
- Las suites administrativas temporales omiten el seed porque crean sus propios admins;
  `tests/integration/test_cuentas_demo.py` lo prueba en bases separadas, incluidos cinco logins,
  permisos, idempotencia, preservación de cuentas y arranques concurrentes.
- Las notas anteriores son históricas; el estado de las ramas ya es el integrado aquí.


Actualizado el 21 de octubre de 2026. Este documento resume el estado observado y
el trabajo pendiente para continuar en el mismo repositorio. Confirmar el estado vivo
de Git, Docker y las bases antes de basarse en los datos de entorno anotados aquí.

## Actualización 22 de octubre de 2026

- Firestore conectado (Admin SDK, `firebase-admin==7.7.0`) al proyecto
  `proyectobases2-83f2e`, base `(default)`. Clave en `.secrets/firebase-adminsdk.json`
  (ignorada por Git/Docker). `python -m scripts.probar_firestore` verifica la conexión.
- Esqueleto de las cinco operaciones del curso: dominio (`paciente.py`, `consulta.py`),
  puertos (`historial.py`), casos de uso, rutas y permisos. Las piezas que un motor no
  implementa lanzan `OperacionPendiente` (HTTP 501). Estado por motor en
  `docs/operaciones_comunes.md`.
- Firestore implementa registrar y leer paciente con `WriteBatch` en la unidad de
  trabajo. Modelo de consultas/archivo pendiente: `docs/modelo_odontologia.md`.
- Proyecto ahora también en `C:\Users\henry\OneDrive\...\Proyecto_Bases_DatosII`.

## Actualización 1 de noviembre de 2026 (rama `Backend/hospital-pediatrico`)

- Se fusionó `Develop`. La administración en dos niveles es la de `Develop`: la implementación
  propia de esta rama (commit `d611ab6`) se descartó al fusionar y queda solo en el historial.
- Lo propio de esta rama es el Centro Pediátrico alineado con la pantalla «Facturación» del
  mockup: factura a nombre del tutor (`facturado_a`) y anulación. Migraciones MySQL `015` y `016`.

## Actualización 31 de octubre de 2026 — Clínica Odontológica

Rama `Clinica-Odontologica`, que parte de `Develop`. El backend de la clínica coincide con el
mockup y el contrato por pantalla está en `docs/contrato_clinica_odontologica.md`. Se corrigió:
pieza contra baja simultánea, 500 al agotar reintentos, consulta de alergias por la secretaria
(afecta a la ruta común de los cuatro motores) y permisos por defecto del `odontologo`.

Las pruebas de `tests/integration/test_firestore.py` pasan contra el proyecto real. Con el
emulador 1.19.8 las de concurrencia se omiten. Lo administrativo del mockup para la clínica
viene de `Develop`, ya fusionada en esta rama.

## Estado vigente (23 de octubre de 2026, noche) — leer primero

Esta sección corrige lo que dicen las actualizaciones históricas de más abajo.

- Los cuatro motores implementan registrar, leer, **buscar por nombre**, historial,
  consulta (diagnósticos, tratamientos, recetas) y archivar. Citas, adendas y corrección de datos
  también en los cuatro; odontograma solo en Firestore, crecimiento/vacunas solo en MySQL y
  órdenes de laboratorio solo en MongoDB (ver `documentacion-backend.md`, que manda sobre
  lo histórico de abajo). Detalle, migraciones para volúmenes existentes y diseño de consistencia en
  `docs/operaciones_comunes.md`; porcentajes en `docs/avance.md` (backend ≈ 98 %).
- Un commit por motor: `feat(postgresql)`, `feat(mysql)`, `feat(mongodb)` (autor HDZaid).
  Archivos nuevos: `app/infrastructure/persistence/{postgresql,mysql,mongodb}/unidad.py`
  (el antiguo `mongodb/lectura.py` pasó a `unidad.py`; `sql.py` solo queda como esqueleto
  que usan algunas pruebas unitarias), `persistence/comun.py` (ayudantes comunes),
  migraciones `postgresql/008`, `mysql/004` y `mysql/005`, y `tests/integration/test_*_api.py`.
- MongoDB sigue siendo servidor único: las escrituras se acumulan hasta `commit()` y la
  consulta usa una escritura condicional previa como punto de serialización con la baja.
  La cuenta `historiales_app` conserva el rol `readWrite` (MongoDB no permite limitarlo
  por operación sin un rol personalizado); definir uno si se quiere el mínimo estricto.
- Las cuentas SQL de la API no pueden borrar datos clínicos; MySQL tampoco ve el salario.
- Frontend: sin construir (HTML/JS servido por FastAPI; plan en `docs/frontend.md`).
- Las pruebas de integración se ejecutaron contra PostgreSQL 16, MySQL 8.0 y MongoDB 8.0
  locales; falta verificar el arranque desde cero con `docker compose` (MySQL 8.4).

## Actualización 23 de octubre de 2026

Decisiones del equipo: cada institución guarda solo sus pacientes (contacto y
alergias opcionales en el contrato común); rol `secretaria` que registra pacientes
y gestiona citas sin acceso clínico; la clínica odontológica agenda citas y lleva
odontograma.

- Firestore completo (pacientes, contacto/alergias, consultas, archivo, citas con
  candado por día, odontograma FDI, perfiles de profesionales). Probado contra el
  proyecto real con `tests/integration/test_firestore.py`. Modelo y justificación en
  `docs/modelo_odontologia.md`.
- `database/postgresql/006_rol_secretaria_citas.sql`: rol, permisos `citas:*` y
  triggers que impiden permisos clínicos a la secretaria (aplicar a mano en
  volúmenes existentes). `scripts/sincronizar_profesionales.py` copia perfiles a Firestore.
- Avance estimado en `docs/avance.md`. El frontend no existe todavía.

## Actualización 23 de octubre de 2026 (noche)

Decisiones nuevas del equipo, ya aplicadas en código y documentos:

- Frontend: HTML/JS sencillo servido por FastAPI (no React). Sin construir todavía;
  faltan mockups. Plan en `docs/frontend.md`.
- La secretaria no archiva, y existe solo en `clinica_odontologica`
  (`database/postgresql/007_secretaria_restricciones.sql`, `permisos.PERMISOS_VEDADOS_SECRETARIA`,
  validación en `scripts/crear_profesional.py`). Alergias: opcionales; la secretaria
  puede anotarlas pero la API no se las devuelve.
- Odontograma: el estado de la pieza sale de una lista fija (`EstadoDental` en
  `app/domain/odontograma.py`); la API responde 422 con otro valor.
- Hueco conocido: no hay búsqueda de pacientes por nombre (solo por ID).

## Objetivo y decisiones del equipo

Es un proyecto académico de Bases de Datos II: una aplicación cliente-servidor con
FastAPI que consulta historiales clínicos almacenados en cuatro motores distintos.
El PDF del curso en la raíz es la fuente para la rúbrica; sus requisitos deben
distinguirse de las preferencias del equipo. La rúbrica plantea operaciones comunes
en los motores, enrutamiento por institución, consistencia, controles de acceso,
clasificación de información, y explicar decisiones de modelado/transacciones.
SQLite y otros motores ligeros están prohibidos por el enunciado.

El equipo eligió esta distribución:

| Institución | Motor | Progreso en la última revisión |
| --- | --- | --- |
| Hospital General | PostgreSQL | SQL clínico original preservado; esquema de identidad central; adaptador de lectura. |
| Centro Pediátrico | MySQL 8.4 | Modelo revisado, reglas de integridad y adaptador de lectura. |
| Laboratorio Clínico | MongoDB 8 | Script de colecciones, validadores e índices; adaptador de lectura. |
| Clínica Odontológica | Cloud Firestore | Pendiente; el equipo eligió conectar el SDK Admin de Python directamente al proyecto cloud, sin exigir emulador local. |

La identidad común vive en PostgreSQL. Solo los profesionales de salud inician
sesión y cada cuenta pertenece a un establecimiento. El backend obtiene de la cuenta
verificada el motor que debe consultar; el cliente no elige la institución enviando
un parámetro o una cabecera. Las bases clínicas mantienen sus propios historiales.
No se usa Firebase Auth para reemplazar la identidad central.

El usuario está aprendiendo. Explicar en español, con claridad y de forma amable,
cualquier corrección conceptual. Mantener como criterio continuo revisar huecos de
información e integridad de los datos; no inventar reglas clínicas sin fundamento.

## Estado del repositorio observado

- Rama `main`, último commit observado `ee7f4b7` (`Estructura base del proyecto`),
  árbol de trabajo limpio antes de preparar este relevo. La documentación de estado
  quedó modificada para registrar el relevo y la decisión de Firestore; `README.md`,
  este documento, `docs/decision_firestore.md`, `docs/ramas.md`,
  `docs/identidad_central.md` y `docs/arquitectura.md` siguen pendientes de revisión
  y commit. No se implementó el adaptador de Firestore.
- El usuario pidió terminar primero la base común y después organizar motores en
  ramas. No se habían creado ramas de motor.
- Proyecto en `C:\Users\geova\OneDrive\Escritorio\Proyecto Bases de Datos II`.
  Windows y PowerShell; el entorno `.venv` usa Python 3.12. En Windows conviene
  instalar/ejecutar comandos como `python -m pip` y `python -m uvicorn` desde la raíz.
- `.env` existe y está ignorado por Git. **No leerlo en la terminal, imprimirlo,
  sustituirlo ni copiar secretos a documentación.** `python -m scripts.configurar_desarrollo`
  agrega únicamente claves faltantes y conserva los valores existentes.
- Último intento de consultar Compose el 21 de octubre de 2026: Docker Desktop no
  estaba disponible (`dockerDesktopLinuxEngine` no respondió). No asumir que las
  bases, la API, los puertos o los volúmenes estén ahora activos.
- Las instrucciones que compartió el usuario indican que Postman CLI está instalado
  y se puede usar para trabajo de API. No apareció un archivo `AGENTS.md` dentro del
  repositorio durante la inspección.
- En una verificación anterior (5 de octubre) las cuentas estaban vacías, los tres
  motores y la API en Docker estaban sanos, y la suite dio 40 pruebas aprobadas con
  integraciones activadas. Es un resultado histórico, no una comprobación del estado
  actual. Verificar los datos locales antes de migrar o modificar volúmenes.

## Archivos de referencia

- `README.md`: arranque, rutas, perfiles de Compose y comandos de prueba.
- `Proyecto final bases II (1).pdf`: enunciado del curso en la raíz. Sus instrucciones
  de entrega se deben contrastar con lo pedido por el usuario.
- `app/`: dominio, casos de uso, puertos, rutas FastAPI, dependencias y fábrica.
- `app/bootstrap/factory.py`: decide el adaptador configurado por institución.
- `app/infrastructure/identity/`: autenticador JWT y directorio PostgreSQL.
- `app/infrastructure/persistence/`: lectura inicial en SQL y MongoDB.
- `database/postgresql/001_hospital_general.sql`: copia del esquema clínico inicial.
- `database/postgresql/002_identidad.sql` a `005_proteger_login.sql`: directorio,
  relación con el personal del hospital, permisos SQL y bloqueo por intentos.
- `database/mysql/original/DB Hospital MySql.sql`: copia intacta del SQL recibido.
- `database/mysql/001_hospital_pediatrico.sql`: esquema revisado que se ejecuta sobre
  una base vacía; **no es una migración** del SQL original.
- `database/mysql/002_integridad.sql` y `003_permisos.sql`: triggers y cuenta de
  lectura de la API.
- `laboratorio_clinico_mongo.js` en la raíz: creación idempotente de colecciones y
  validadores. `docs/modelo_laboratorio.md` explica sus decisiones y límites.
- `docs/revision_mysql.md`: cambios al modelo pediátrico, integridad y temas pendientes.
- `docs/identidad_central.md`: login, roles, permisos y creación administrativa de cuentas.
- `docs/arquitectura.md`: flujo por capas y límites de las unidades de trabajo.
- `docs/ramas.md`: estrategia deseada de integración, todavía sin ramas creadas.
- `scripts/configurar_desarrollo.py` y `scripts/crear_profesional.py`: preparación
  local y alta interactiva de una cuenta. La API no ofrece autorregistro.

## Qué funciona y qué no

`POST /api/v1/auth/login` acepta correo y contraseña, valida el hash Argon2id en
PostgreSQL y entrega un JWT HS256 breve. En cada solicitud se vuelven a comprobar
cuenta activa, establecimiento, permisos y versión del token. El cierre de sesión
incrementa la versión e invalida las sesiones vigentes. Cinco contraseñas fallidas
bloquean la cuenta durante quince minutos. El endpoint de login no acepta un motor o
establecimiento proporcionado por el cliente.

`GET /api/v1/auth/me` y `GET /api/v1/pacientes/{id_paciente}` están implementados.
La lectura de paciente ya se ha probado en PostgreSQL, MySQL y MongoDB. Los ID son
texto en el contrato HTTP: PostgreSQL/MySQL usan ID numéricos locales y MongoDB un
`ObjectId`. Los adaptadores normalizan esos formatos a la respuesta común.
Las fábricas de Firestore y todas las operaciones clínicas de escritura siguen
pendientes. La interfaz gráfica también sigue pendiente.

El perfil Compose `api` ejecuta la API; `docker compose up -d postgres mysql mongo`
solo solicita motores. Puertos predeterminados: PostgreSQL 5434, MySQL 3307,
MongoDB 27018 y API 8000, limitados a `127.0.0.1`. Los scripts SQL/JS de Docker se
ejecutan al inicializar un volumen vacío, no cada vez que se reinicia el contenedor.
Un cambio de esquema posterior requiere migración controlada. No usar `docker compose
down -v` para resolver discrepancias sin confirmar antes qué datos se borrarían.

## Pendientes recomendados

1. Leer el PDF y las decisiones documentadas antes de editar; confirmar el estado de
   Git y Compose. Arrancar Docker solo si la tarea de continuación lo requiere.
2. Acordar contratos HTTP y entidades comunes para las cuatro operaciones del curso:
   registrar paciente, consultar historial, registrar atención con diagnóstico,
   tratamientos y recetas, y archivar expediente. Definir sus permisos, paginación,
   validación y reglas de archivo antes de replicarlas en los cuatro adaptadores.
3. Completar el modelo común y sus casos de uso, conservando las respuestas y reglas
   compartidas. Reutilizar los puertos y el patrón de unidad de trabajo existentes.
4. Implementar Firestore para la Clínica Odontológica usando el SDK Admin de Python
   desde FastAPI, conectado al servicio cloud. El equipo considera que, con poco
   tiempo, una instancia cloud existente evita sumar Firebase CLI y Emulator Suite.
   Aún hay que confirmar que tienen acceso a un proyecto y credenciales: si no lo
   tienen, reevaluar el emulador como alternativa de desarrollo. Consulta
   `docs/decision_firestore.md` para el procedimiento, IAM, costos y seguridad.
   Mantener las credenciales fuera de Git y de la imagen Docker; el servidor Admin
   SDK queda autorizado por IAM y la API debe aplicar los permisos del usuario en
   PostgreSQL/JWT. Usar únicamente datos sintéticos de demostración.
5. Antes de ofrecer escrituras, agregar auditoría y rectificación clínica. En MongoDB,
   validar existencia y relación de paciente/consulta/profesional en el adaptador:
   MongoDB no aplica llaves foráneas. La instancia Compose actual es standalone;
   operaciones atómicas de varios documentos requieren un replica set y pruebas de
   transacciones. No prometer transacciones entre motores. La cuenta `historiales_app`
   se crea con rol `readWrite` aunque el adaptador actual solo lee; antes de ofrecer
   escrituras, definir los permisos mínimos requeridos por la API.
6. Revisar el SQL clínico original de PostgreSQL antes de habilitar sus pagos y
   hospitalizaciones: hay reglas de pagos que no cubren concurrentemente cambios o
   eliminaciones, posible solapamiento de ocupación de camas, y falta validar que la
   cita y la atención correspondan al mismo paciente. `docs/arquitectura.md` ya lo
   señala como trabajo previo a esos módulos.
7. Mantener las mejoras de MySQL compatibles con el propósito pediátrico. `docs/revision_mysql.md`
   distingue reglas reforzadas de decisiones que debe acordar el equipo, como unidades
   de inventario, aplicadores que no sean médicos y procesos de rectificación.
8. Recién cuando la base común esté acordada, organizar el desarrollo en las ramas
   de motores previstas en `docs/ramas.md` y luego integrar los cuatro adaptadores.
   No cambiar de rama para simular el enrutamiento de la aplicación.
9. Completar la clasificación de datos y la comparación académica de los cuatro
   modelos: normalización y restricciones en SQL, documentos/embebido/referencias en
   MongoDB, y consistencia y transacciones. No asumir que un comentario de esquema
   sustituye autorización.

Pruebas de integración existentes: fijarse en `tests/integration/`. En la ejecución
anterior, MySQL usó una base temporal con nombre de prueba y se eliminó al terminar;
las pruebas de PostgreSQL y MongoDB insertaron registros sintéticos y los limpiaron.
La variable `HISTORIALES_TEST_INTEGRATION=1` las activa. Revisar primero la fixture
antes de correrla, especialmente si cambió para proteger los datos del entorno local.
No publicar un correo, contraseña o token fijo en ejemplos.

## Modo de trabajo al continuar

El usuario pidió que las mejoras prioricen consistencia e integridad y que se expliquen
las correcciones. Separar claramente los requisitos del PDF de las decisiones del
equipo. Hacer cambios en el proyecto y documentar pruebas/límites reales; no informar
como activo un servicio cuyo estado no se haya verificado.

Este relevo describe lo que se observó el 21 de octubre de 2026 y lo que ya estaba
documentado. Las bases y los servicios pueden haber cambiado después.
