# REDESIGN_AUDIT.md

## Historiales — Auditoría del repositorio (Fase 1, solo lectura)

Fecha: 24 de octubre de 2026 · Base auditada: `origin/main` (6465dbc) · Autor: Claude (sesión de identidad visual)

Este documento responde a la Fase 1 de `REDESIGN_BRIEF.md`. No se modificó ningún archivo de código, de
configuración ni de pruebas. El único archivo nuevo de esta fase es este. Antes de la auditoría se resolvió,
a pedido del usuario, un merge de git atascado (ver §10.1); eso no cambió contenido del proyecto.

---

## 0. Resumen ejecutivo

1. **No existe frontend.** El brief habla de "rediseñar" y de "conservar la integración existente", pero en el
   repositorio no hay HTML, CSS, JS, plantillas, `StaticFiles` ni `package.json`. Lo único real es la
   decisión escrita en `docs/frontend.md` ("tecnología decidida, nada construido"). El trabajo es una
   **construcción desde cero**, con el mockup como referencia visual.
2. **El backend ya está listo** para soportarlo: API REST versionada en `/api/v1`, JWT, permisos por rol,
   enrutado por institución desde el token y errores con un formato uniforme.
3. **Se puede dejar el backend intacto y sin Node.js** en producción ni en desarrollo: HTML + CSS + módulos
   ES nativos, copiados bajo `app/` y servidos por la misma FastAPI. La única pieza de backend que se
   toca es **montar una carpeta estática** (≈3 líneas en `app/main.py` + un módulo nuevo). Requiere tu
   aprobación expresa (D1).
4. **El mockup es aprovechable como sistema visual y como arquitectura de componentes, no como producto.**
   Contiene pantallas con datos que el API no ofrece (camas, emergencias, pagos, facturación, lotes de
   vacunas, edición del catálogo de laboratorio). Hay que omitirlas o mostrarlas vacías con honestidad.
5. **Faltan datos que la interfaz querrá mostrar** (nombre y rol del usuario, lista de profesionales, colas de
   trabajo). Se pueden resolver sin tocar el backend con recortes de diseño; ver §6.
6. Hay **8 decisiones** que necesito de ti antes de implementar (§11).

---

## 1. Alcance y método

Inspeccionado (solo lectura, a través del puente al equipo del usuario): `REDESIGN_BRIEF.md`,
`README.md`, `docs/*.md`, `documentacion-backend.md`, `app/main.py`, `app/presentation/api/` completo
(rutas, schemas, dependencias, manejadores), `app/domain/permisos.py` e `institucion.py`,
`app/core/config.py`, `Dockerfile`, `.dockerignore`, `compose.yaml`, `requirements*.txt`, `pyproject.toml`,
`.env.example` (nunca `.env`), `tests/` (estructura y dobles), `scripts/` (nombres) y `git status/log`.

No se ejecutó la aplicación ni las bases de datos. Todo lo que dice este documento sobre comportamiento
viene del código y de la documentación, no de una ejecución.

---

## 2. Estado real del frontend

| Pregunta del brief (§11, Fase 1) | Hallazgo |
|---|---|
| ¿Framework, templates, CSS, JS? | **Ninguno.** No hay archivos `.html/.css/.js` de interfaz en el repo. |
| ¿Proceso de build? | **Ninguno.** No hay `package.json`, `vite.config`, `webpack`, `node_modules`. |
| ¿Cómo entrega FastAPI el frontend hoy? | **No lo entrega.** No hay `StaticFiles`, `Jinja2Templates` ni `FileResponse`. `GET /` devuelve JSON `{nombre, version, docs}`. |
| ¿Rutas, vistas, roles consumidos? | Ninguna vista existe. El plan de pantallas está en `docs/frontend.md` §"Pantallas" y es consistente con el API (§5). |
| ¿Pruebas del frontend? | Ninguna. Las pruebas son del backend (`pytest`, `tests/`, con dobles en memoria `tests/doubles.py`). |
| ¿Dónde está el mockup? | **No está en el repo.** Vive en el chat de identidad visual; el usuario adjuntó la v1 (2 583 líneas) y es equivalente a la versión final del chat salvo por el envoltorio HTML del artefacto. |

Consecuencias:

- "No crear un frontend paralelo que duplique la aplicación actual" (brief §9) se cumple trivialmente:
  no hay nada que duplicar. Sí hay que respetar **la decisión ya tomada por el equipo** en `docs/frontend.md`.
- "Conservar nombres, formatos y flujos de datos que consume el frontend" (brief §10) se traduce en
  **conservar el contrato del API** tal como está (§5). No hay otro contrato que preservar.
- El brief §10 pide identificar estados "de carga, error, vacío y éxito que existen": no existen; se
  definirán en Fase 2 siguiendo la tabla de errores del API (§5.3).

---

## 3. Arquitectura y servidor actuales

```
app/
  main.py                      create_app(): CORS (solo si se configura), manejadores, /health, /api/v1, GET /
  bootstrap/                   contenedor de dependencias y fábrica de motores
  core/                        configuración (pydantic-settings, prefijo HISTORIALES_), auditoría
  domain/                      entidades, errores, permisos, institución
  application/                 casos de uso y puertos
  infrastructure/persistence/  adaptadores PostgreSQL / MySQL / MongoDB / Firestore
  presentation/api/            router, rutas, schemas, dependencias, manejadores   <- único "presentation" hoy
```

- **Arquitectura hexagonal**; `presentation/` solo contiene `api/`. Es el lugar natural para un hermano
  `presentation/web/` (el que ya propone `docs/frontend.md`).
- **CORS cerrado por defecto** (`HISTORIALES_CORS_ORIGINS=[]`). Con frontend en el mismo origen no hace
  falta abrirlo, lo que reduce superficie de ataque.
- **Rutas fuera de `/api/v1`:** `GET /`, `GET /health`, `GET /health/ready`, `/docs`, `/openapi.json`.
  Un montaje en `/app` no choca con nada.
- **Docker:** `Dockerfile` (python:3.12-slim, usuario sin privilegios) copia solo `./app`; ejecuta
  `python -m uvicorn app.main:app` en el puerto 8000. Todo lo que viva bajo `app/` entra en la imagen.
- **`compose.yaml`:** perfil `api` publica el 8000; los tres motores locales y Firestore (nube) son aparte.
- **Ejecución local documentada (README):** `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.

---

## 4. Dependencias

- **Producción/Desarrollo Python:** fastapi 0.142.2, uvicorn, pydantic(-settings), psycopg, PyMySQL, pymongo,
  pwdlib[argon2], PyJWT, firebase-admin, tzdata. `requirements-dev.txt` agrega las de prueba.
- **JavaScript:** ninguna. No hay `node_modules`, `package.json` ni CDN.
- **Fuentes e íconos:** ninguno en el repo. El brief pide Inter y "Lucide si ya está presente": **no está**.
- **Observación:** `starlette.staticfiles.StaticFiles` ya viene con FastAPI; el montaje estático no agrega
  ninguna dependencia nueva.

---

## 5. Contrato del API que consumirá la interfaz

Todo bajo `/api/v1`. Autenticación `Authorization: Bearer <JWT>` (30 min, sin endpoint de refresco). La
institución sale **siempre del token**, nunca de un parámetro: la interfaz no elige motor.

### 5.1 Endpoints y permiso exigido

| Vista / acción | Endpoint | Permiso |
|---|---|---|
| Login | `POST /auth/login` `{correo, password}` → `{access_token, expires_in, usuario{id_usuario, institucion, permisos[]}}` | — |
| Sesión | `GET /auth/me` → `{id_usuario, institucion, permisos[]}` · `POST /auth/logout` (204) | token |
| Buscar paciente | `GET /pacientes?nombre=&limite=` (nombre ≥ 2 caracteres, límite ≤ 50) | `pacientes:leer` |
| Ficha | `GET /pacientes/{id}` | `pacientes:leer` |
| Registrar / corregir | `POST /pacientes` · `PATCH /pacientes/{id}` | `pacientes:registrar` |
| Alergias | `POST /pacientes/{id}/alergias` | `pacientes:registrar` |
| Citas del paciente | `GET /pacientes/{id}/citas` | `citas:leer` |
| Historial (cursor) | `GET /pacientes/{id}/historial?limite=&antes_de=` | `historiales:leer` |
| Nueva consulta | `POST /pacientes/{id}/consultas` | `consultas:registrar` |
| Consulta / adenda | `GET .../consultas/{id}` · `POST .../adenda` | leer / registrar |
| Archivar historial | `POST /pacientes/{id}/archivo` | `historiales:archivar` |
| Agenda | `GET /citas?desde=&hasta=&id_profesional=` (zona obligatoria, máx. 31 días) | `citas:leer` |
| Agendar / estado | `POST /citas` · `POST /citas/{id}/estado` (`atendida`, `cancelada`+motivo, `no_asistio`) | `citas:gestionar` |
| Odontograma (solo Clínica) | `GET /pacientes/{id}/odontograma` · `PUT .../odontograma/piezas/{pieza}` | `historiales:leer` / `consultas:registrar` |
| Pediatría (solo Centro) | `GET .../crecimiento`, `POST .../controles`, `GET /vacunas`, `GET/POST .../vacunacion`, `POST .../vacunacion/{id}/aplicar` | leer: `historiales:leer`; escribir: `consultas:registrar` |
| Laboratorio (solo Laboratorio) | `GET /laboratorio/pruebas`, `POST/GET .../ordenes`, `POST .../muestras`, `PUT .../resultados`, `POST .../validar`, `POST .../cancelar` | leer: `historiales:leer` **o** `laboratorio:resultados`; muestras/resultados: `laboratorio:resultados`; validar: `laboratorio:validar`; crear/cancelar orden: `consultas:registrar` |

Los permisos llegan en `/auth/me`; **la interfaz decide qué mostrar solo a partir de ellos** y nunca por
nombre de rol (el rol no viaja; ver §6).

Perfiles reales (de `app/domain/permisos.py`): profesional clínico (`pacientes:leer` + `historiales:*` +
`consultas:registrar`), **laboratorista** (`pacientes:leer`, `laboratorio:resultados`, `laboratorio:validar`),
**secretaria** (solo Clínica Odontológica: `pacientes:leer/registrar`, `citas:leer/gestionar`; sin historial,
sin odontograma, sin archivo y con `alergias: null`).

### 5.2 Reglas de datos que la UI debe respetar

- **Alergias en tres estados:** campo omitido o `null` → "no registradas" (o sin permiso); `[]` → "sin
  alergias conocidas"; lista → mostrarla. Nunca mostrar `[]` cuando llega `null`.
- El **Centro Pediátrico exige fecha de nacimiento** al registrar (`docs/frontend.md`); en las demás es opcional. El formulario cambia según `institucion`.
- Fechas con zona (`AwareDatetime`) en citas, muestras y filtros de agenda; la agenda opera en
  `HISTORIALES_ZONA_HORARIA` (America/Guatemala).
- Odontograma FDI: 12 estados por pieza, superficies `oclusal|incisal|mesial|distal|vestibular|lingual|palatino`
  (máx. 7), nota ≤ 500. Firestore únicamente.
- Resultados de laboratorio: el valor puede ser número, texto o booleano según `tipo_valor`; la
  `interpretacion` y la `referencia` vienen calculadas por el servidor (la UI no las recalcula).
- Una orden validada ya no se modifica (409 si se intenta).

### 5.3 Errores (`handlers.py`)

| Código | Cuándo | Qué hace la UI |
|---|---|---|
| 401 | sin token, token inválido o vencido | limpiar sesión y volver al login con aviso |
| 403 | falta permiso o profesional no vinculado | mensaje del API, sin reintento |
| 404 | paciente/cita/consulta/registro inexistente | estado vacío o "no encontrado" |
| 409 | paciente archivado, choque de agenda, estado inválido | mostrar el `detail` del API tal cual |
| 422 | validación (FastAPI devuelve `[{loc,msg,type}]`; el dominio devuelve texto) | marcar el campo por `loc`; si es texto, mensaje general |
| 501 | operación no implementada en el motor de esa institución | "Función no disponible para tu institución" |
| 503 | autenticación o integración sin configurar | pantalla de servicio no disponible |

Formato uniforme: `{"detail": "..."}` o `{"detail": [...]}`; el 422 de FastAPI **no refleja** el valor enviado
(se filtró `input` para no devolver contraseñas).

---

## 6. Huecos del API frente a lo que la interfaz querrá mostrar

El backend se mantiene intacto, así que cada hueco se resuelve recortando el diseño, **no inventando datos**
(brief §10.3). Cada fila es una decisión de diseño abierta si quieres otra cosa.

| Hueco | Consecuencia | Propuesta sin tocar backend |
|---|---|---|
| `/auth/me` y el login **no devuelven nombre ni rol** del usuario | No se puede saludar "Dra. Pérez" ni mostrar "Odontóloga" | Mostrar el correo escrito en el login y la **institución**; rol deducido de permisos solo como etiqueta genérica ("Laboratorio", "Recepción") o no mostrarlo. *(Alternativa: pedir al backend dos campos; ver D6.)* |
| No hay listado de profesionales | `POST /citas` pide un `id_profesional` UUID | Derivar profesionales de la agenda ya cargada, o campo UUID/selector del profesional con sesión iniciada ("agendar conmigo"). Decisión D5. |
| No existen "colas": todos los pacientes, órdenes pendientes, consultas del día | Los paneles con "pendientes", "en espera", "órdenes por validar" del mockup no tienen fuente | Paneles basados en **agenda del día** (`GET /citas`) donde hay citas (las 4 instituciones) y **búsqueda de paciente** como punto de entrada. Laboratorio: se llega a las órdenes por paciente. |
| Búsqueda exige ≥ 2 caracteres y no lista "recientes" | Tabla de pacientes inicial vacía | Estado vacío con campo de búsqueda protagonista. |
| No hay camas, emergencias, pagos, facturación, lotes/stock de vacunas, edición de catálogo de pruebas | Pantallas del mockup sin API | **Omitir** (D4). Decisión del equipo: el Centro no controla stock de vacunas. |
| `siguiente_antes_de` (cursor) en vez de páginas numeradas | No hay "ir a la página 3" | Botón "Cargar anteriores". |
| Sin refresco de token (30 min) | Sesiones largas expiran de golpe | Aviso de expiración próxima + volver al login conservando la ruta. Sin modificar backend. |

---

## 7. Mockup vs. realidad

Mockup = `Identidad visual Historiales` (v3). Un solo archivo, JS plano, `h()`/`sv()`, estado global `S`,
temas por variables CSS en `.app[data-tema=…]`.

| Elemento | Veredicto | Notas |
|---|---|---|
| Arquitectura: JS plano, helpers `h()` y `sv()` (sin `innerHTML`) | **Reutilizar** | Coincide con la regla de seguridad de `docs/frontend.md`. Se divide en módulos ES. |
| Temas por variables CSS (`data-tema`) | **Reutilizar** | Es exactamente lo que pide el brief (base neutra + acento por institución). |
| Login neutro con logo de 4 cuadrados; tema se aplica **después** de autenticar | **Reutilizar** | Consistente: la institución solo se conoce tras `POST /auth/login`. |
| Odontograma: vista Diente/Cubo + tabla de detalle, 12 estados | **Reutilizar y conectar** | Es lo más cercano a producto; mapea 1:1 al schema (`estado`, `superficies`, `nota`). |
| Citas / agenda, pacientes, ficha con alergias tri-estado, historial | **Adaptar** | Datos reales del API; estados vacío/carga/error nuevos. |
| Laboratorio: catálogo de pruebas, orden, muestras, resultados con referencia, validación | **Adaptar** | Existe API completa. |
| Pediatría: crecimiento (peso/talla/perímetro/percentiles), calendario de vacunación | **Adaptar** | Existe API; gráfica de percentiles solo si caben datos reales. |
| Hospital: camas, emergencias, pagos | **Descartar (demostrativo)** | Sin API. |
| Pediatría: lotes/stock y facturación; Laboratorio: gestión del catálogo | **Descartar (demostrativo)** | Sin API / decisión del equipo. |
| Barra de revisión del mockup (cambiar de tema a mano, etc.) | **No es producto** (brief §3) | Se elimina; el tema lo fija `institucion`. |
| Tipografías propias por institución, bordes gruesos | **Descartar** | Contradice el brief (Inter única, bordes finos `#DCE5EC`). |
| Íconos propios | **Rehacer** | Lucide no está en el repo (§9.4). |
| Choque de nombres `.in` y `[hidden]` | **Corregir al migrar** | Prefijar clases; regla `[hidden]{display:none!important}`. |

---

## 8. Conflictos entre el brief y la arquitectura real

| # | Conflicto | Resolución propuesta |
|---|---|---|
| C1 | Brief asume frontend existente; no existe | Tratar como construcción, con tu confirmación (D2). |
| C2 | `Identidad visual Historiales.html` no está en el repo | Guardarlo en `docs/referencia/` como referencia, **fuera de `app/`** (no se sirve ni entra a la imagen) (D8). |
| C3 | Brief: "Lucide solo si ya está presente"; no lo está, y la CSP `default-src 'self'` impide CDN | Sprite SVG local propio con ~30 íconos dibujados a mano en trazo de 1.75 px, estilo Lucide pero **sin copiar** el paquete (D3). |
| C4 | Brief pide Inter; sin CDN | Alojar Inter en `.woff2` local (licencia OFL, se incluye el texto de la licencia). |
| C5 | "Backend intacto" vs. necesidad de montar estáticos | Un único cambio aditivo en `app/main.py` (D1); comportamiento del API no cambia. |
| C6 | Servidor Windows y `mimetypes` | Python toma los tipos MIME del **registro de Windows**; si `.js` figura como `text/plain`, el navegador rechaza los módulos ES. Se registran explícitamente `.js`, `.css`, `.svg` y `.woff2` al montar. |
| C7 | `StaticFiles(html=True)` no hace *fallback* a `index.html` en rutas profundas | Enrutador por `#/` (hash); evita añadir un *catch-all* al backend. |
| C8 | CSP por cabecera necesitaría *middleware* | `<meta http-equiv="Content-Security-Policy">` en `index.html` (D7). |
| C9 | Brief: Pediátrico sin paleta secundaria; Dental con pasteles pendientes y `#f5722` inválido | Proponer paletas en Fase 2 y pedir aprobación antes de Fase 3 (brief §11). |
| C10 | `.dockerignore` contiene `*.js`, `*.sql`, `*.pdf`, `docs` | **Hipótesis corregida:** en `.dockerignore` un patrón sin `**/` solo aplica a la raíz del contexto, por lo que `app/presentation/web/*.js` **no** queda excluido (solo `laboratorio_clinico_mongo.js` de la raíz). Se verificará con `docker build` en Fase 2 y solo se añadirá una negación si fallara. |

---

## 9. Propuesta técnica

### 9.1 Tecnología

- **HTML + CSS (variables) + módulos ES nativos.** Sin framework, sin bundler, sin transpilación, sin Node,
  ni siquiera en desarrollo. Es lo decidido en `docs/frontend.md` y lo que pide el brief ("no migrar a
  React/Vite/Jinja2 solo por modernizar").
- Archivos servidos tal cual por `StaticFiles` → **no hay proceso Node en producción porque no hay nada
  que compilar**. El artefacto de despliegue son los mismos archivos del repositorio.

### 9.2 Estructura

```
app/presentation/web/
  __init__.py                 montar_frontend(app): registra MIME y monta /app (StaticFiles, html=True)
  index.html                  único documento; <meta CSP>; carga js/main.js como módulo
  assets/
    fonts/Inter-Variable.woff2, OFL.txt
    icons/sprite.svg
  css/
    tokens.css                color, tipografía, radios, espaciado, sombras (variables)
    base.css  componentes.css  layout.css
    temas/dental.css  hospital.css  laboratorio.css  pediatrico.css   (solo sobrescriben acento/superficies)
  js/
    main.js  api.js  sesion.js  enrutador.js  permisos.js
    ui/dom.js (h, sv)  ui/iconos.js  ui/componentes.js (tabla, drawer, modal, toast, estados)
    vistas/login.js  inicio.js  pacientes.js  ficha.js  citas.js  historial.js
    vistas/odontograma.js  vistas/pediatria.js  vistas/laboratorio.js
docs/referencia/identidad-visual-mockup.html     (referencia; no se sirve)
```

Una **misma base** (tokens, componentes y vistas compartidas: pacientes, ficha, citas, historial) con cuatro
temas: el brief exige "verificar que las cuatro puedan usar la misma base sin duplicar pantallas".
Solo odontograma, pediatría y laboratorio son específicas por institución, y el API ya lo impone (501 en
las demás).

### 9.3 Integración con FastAPI (el único contacto con el backend)

En `app/main.py`, junto a las demás inclusiones (3 líneas, aditivas):

```python
from app.presentation.web import montar_frontend
...
montar_frontend(app)        # /app
```

- Mismo origen → **sin CORS**, sin tocar `HISTORIALES_CORS_ORIGINS`, sin cambiar contratos.
- `GET /` seguirá devolviendo su JSON (no se redirige; los tests existentes no se alteran).
- Un test nuevo del montaje (`tests/test_web.py`): `/app/` responde 200, `.js` sale como
  `text/javascript`, `index.html` trae CSP; y se comprueba que `/health` y `/api/v1/...` siguen igual.
- Se corre la suite completa existente antes y después para demostrar que no cambió nada.

### 9.4 Cómo se cumplen las promesas del brief

| Requisito | Cómo |
|---|---|
| Backend intacto | Endpoints, schemas, permisos, motores: sin cambios. Solo se agrega un montaje estático y su test. |
| Sin Node en producción | No hay build; se sirven archivos estáticos. Tampoco hace falta en desarrollo. |
| Un solo despliegue | Todo vive bajo `app/`, entra en la imagen existente y sale por el puerto 8000. |
| CSP estricta | `default-src 'self'`; fuentes, íconos y scripts locales; sin `unsafe-inline` ni CDN. |
| Sin XSS | `textContent`/`h()`; nunca `innerHTML` con datos del API. |
| Token | En `sessionStorage` (muere al cerrar la pestaña) o en memoria (D7); nunca `localStorage`. |
| Permisos | Navegación y acciones se generan desde `permisos[]`; el 403 del servidor sigue siendo la autoridad. |
| Accesibilidad | Foco visible, controles por teclado, estados con texto+icono además de color, contraste AA. |
| Movimiento | Transiciones funcionales cortas; `prefers-reduced-motion` las anula. |
| Sin modo oscuro | Todo el color pasa por variables, para añadirlo después sin reescribir. |

### 9.5 Verificación sin Node

- Backend: `pytest` actual (debe seguir en verde, mismo conteo).
- Montaje: `tests/test_web.py` nuevo.
- Visual y de flujo: **Playwright para Python** (paquete `pip`, solo en `requirements-dev.txt`) con el
  `create_app` + dobles en memoria (`tests/doubles.py`) para no depender de las bases de datos, o contra tu
  `docker compose` si lo prefieres. Capturas por institución y rol, y lectura de la consola del navegador
  (brief Fase 4: "sin errores de consola"). Es opcional (D8-bis dentro de D8).

### 9.6 Orden de implementación

Siguiendo los límites de fase del brief y revisando contigo al terminar cada una.

| Fase | Contenido | Entregable que revisas |
|---|---|---|
| **2a** | Montaje estático + test; `index.html`; tokens y base; Inter; sprite; `dom.js`, `api.js`, `sesion.js`, `enrutador.js` | `/app` carga; login neutro funcional (login real) |
| **2b** | Componentes compartidos (tabla, drawer, modal, toast, estados vacío/carga/error, formularios con 422) + propuesta de paletas pendientes | Página de componentes + paletas Pediátrico/Dental para aprobar |
| **3.1** | **Dental:** pacientes, ficha, citas, historial, **odontograma** (Diente/Cubo + tabla), vista de secretaria | Capturas + recorrido con usuario clínico y secretaria |
| **3.2** | **Hospital:** pacientes, ficha, historial, consulta, citas, semántica rojo/ámbar | idem |
| **3.3** | **Laboratorio:** órdenes por paciente, muestras, resultados, validación, referencias | idem con laboratorista |
| **3.4** | **Pediátrico:** crecimiento y vacunación (paleta ya aprobada) | idem |
| **4** | Validación global del brief §11 (consola, responsive, permisos, 4 instituciones) y registro de pruebas | informe en `REDESIGN_AUDIT.md` (apéndice) |

### 9.7 Riesgos

| Riesgo | Efecto | Mitigación |
|---|---|---|
| MIME de `.js` en Windows (C6) | Pantalla en blanco | Registro explícito de tipos + test. |
| Expiración de JWT a los 30 min | Pérdida de un formulario largo | Aviso previo, guardar borrador en `sessionStorage`, volver tras re-login. |
| Datos de ejemplo no disponibles en el equipo de demo | Capturas sin contenido | Dobles en memoria y/o `scripts/configurar_desarrollo.py`; no se inventan datos en producción. |
| Contratos distintos por motor (501) | Menús que llevan a error | Navegación por `institucion` + permisos; el 501 se maneja igualmente. |
| Mockup demasiado denso para el API real | Pantallas "vacías" | Diseñar estados vacíos con intención y acciones claras. |
| Tipografía/íconos locales aumentan el peso | Carga más lenta | Inter variable subconjunto latino (~100 KB) y sprite único. |
| CRLF/LF y OneDrive | Ruido en `git status` | `.gitattributes` ya tiene `text=auto`; no se corrige aquí. |
| Zona horaria del navegador ≠ del servidor | Citas mostradas con otra hora | Formatear con `Intl` fijando `America/Guatemala` o la zona de configuración. |

---

## 10. Notas de la sesión

### 10.1 Estado de git

Antes de la auditoría el repo tenía un merge sin resolver. A petición expresa, se dejó `HEAD = origin/main`
(6465dbc) sin conflictos y la rama `Respaldo` (69ab84d) conserva el estado anterior. `git status` puede
listar archivos "modificados" por diferencias de saltos de línea (CRLF/LF) aunque `git diff origin/main`
no muestra cambios de contenido.

### 10.2 Lo que NO se pudo comprobar

- Que la suite `pytest` pase hoy en tu equipo (no se ejecutó).
- Que el `docker build` incluya la carpeta nueva (se verifica en Fase 2a).
- Qué devuelven los motores con datos reales; se infiere de los schemas y de `documentacion-backend.md`.

---

## 11. Decisiones aprobadas (D1–D8)

Aprobadas por el usuario tras la Fase 1. Sustituyen a las recomendaciones de la versión anterior de este apartado.

| ID | Decisión aprobada |
|---|---|
| **D1** | Montar la interfaz en `/app` de forma estrictamente aditiva: no se tocan endpoints, schemas, servicios, repositorios, autenticación, permisos ni motores. `GET /` no cambia. Se incluyen el módulo de integración y sus pruebas. |
| **D2** | Construcción desde cero. El mockup es solo referencia. |
| **D3** | Íconos Lucide originales como SVG estáticos locales, sin Node ni npm, conservando los avisos de licencia (ISC). |
| **D4** | Se omiten las funciones sin API. Hospital usa rojo/naranja solo para estados reales del API; no hay cola de emergencias inventada. |
| **D5** | Verificada (apartado 12). Sin selector de profesional incompleto. Se documenta la limitación y se propone alternativa. |
| **D6** | Sin cambios de backend. Se muestran correo e institución. |
| **D7** | JWT solo en `sessionStorage`, con expiración y avisos. CSP en `<meta>` documentando sus límites. |
| **D8** | Mockup guardado en `docs/referencia/identidad-visual-mockup.html` (solo referencia, no se sirve). Playwright para Python como dependencia solo de desarrollo. |

Decisiones visuales: Hospital `#0068FF` (rojo intenso = emergencias, naranja = gravedad); Pediátrico `#4D8687` con coral `#F19A91`, mantequilla `#F4D990` y menta `#BFDCCF`; Laboratorio `#A75FF1` con degradados moderados hacia violetas más profundos; Clínica `#006977` con pasteles `#E4F0F0`, `#F5D7D2`, `#F3E5D8`, `#D8ECE7`; Inter en toda la interfaz; se conserva la marca de cuatro cuadrados; sistema de diseño compartido. Orden de implementación: Clínica, Hospital, Laboratorio, Pediátrico.

La referencia visual con estas decisiones aplicadas es la maqueta navegable publicada en la conversación (datos sintéticos, mismos nombres de campo que el API).

---

## 12. Verificaciones posteriores a la aprobación

### 12.1 D5: selector de profesional en citas

- `id_usuario` es igual a `id_profesional` (UUID) por construcción: es el `sub` del JWT.
- `CitaResponse` trae `id_profesional` y `creada_por` (UUID), sin nombre del profesional.
- No existe un endpoint que liste profesionales.
- `POST /citas` valida que el profesional exista, esté activo y atienda (422/403 en caso contrario).
- La secretaria no atiende, así que no puede agendar de forma fiable sin un cambio de backend (`GET /profesionales` o un campo de nombre).

**Alternativa propuesta (sin tocar backend):** "Agendar conmigo" para usuarios clínicos (el profesional es la sesión actual). La secretaria ve la agenda y cambia estados de cita, pero no crea citas desde la interfaz. Opción futura, solo si el usuario la pide: `GET /profesionales` o nombre en `CitaResponse`.

### 12.2 `app.frontend()` frente a `StaticFiles`

- FastAPI 0.142.2 instalado sí ofrece `app.frontend(path, *, directory, fallback='auto', check_dir='auto')`: rutas de baja prioridad (después de las del API), `_FrontendStaticFiles(StaticFiles)`, respaldo SPA a `index.html` para navegaciones, `404.html` y redirección de índice de directorio.
- Se apoya igualmente en Starlette `StaticFiles` y en `mimetypes`, por lo que el riesgo de Windows (registro del sistema que sirve `.js` como `text/plain`) sigue existiendo y exige registrar los tipos MIME explícitamente.
- `StaticFiles(html=True)` no tiene respaldo SPA; el enrutador por hash (`#/`) evita necesitarlo.
- **Recomendación:** mantener `StaticFiles` montado en `/app` (lo más simple y compatible, ya documentado en `docs/frontend.md`) y registrar MIME de `.js`, `.css` y `.svg`. `app.frontend()` queda como alternativa opcional si más adelante se quiere rutas sin hash. No cambia la arquitectura.
- Verificar con `docker build` en la Fase 2a que `.dockerignore` no excluya `app/presentation/web/*.js` (los patrones sin `**/` solo aplican a la raíz del contexto).

### 12.3 Correcciones a hechos de la auditoría

- Motivo de baja: `traslado`, `fallecimiento`, `administrativo`.
- Estado de cita: `programada`, `confirmada`, `atendida`, `cancelada`, `no_asistio`.
- Pediátrico tiene además `/vacunacion/esquema-recomendado` y `/vacunacion/{id}/cancelar`.
- `GET /pacientes/{id}` solo devuelve `archivado: bool`; el motivo de archivo no se puede recuperar.

---

## 13. Plan de trabajo actualizado

| Fase | Contenido | Aprobación |
|---|---|---|
| **2a** | Montaje en `/app` (`StaticFiles`), módulo de integración y pruebas, MIME, verificación con `docker build`, CSP en `<meta>` y su documentación de límites (D7) | Al terminar |
| **2b** | Sistema visual compartido: tokens, Inter alojada, íconos Lucide SVG, componentes, cliente HTTP, sesión (`sessionStorage`, expiración y avisos), estados de carga/error/vacío | Al terminar |
| **3.1** | Clínica Odontológica (incluye odontograma) | Al terminar |
| **3.2** | Hospital General | Al terminar |
| **3.3** | Laboratorio Clínico | Al terminar |
| **3.4** | Centro Pediátrico | Al terminar |
| **4** | Validación global (Playwright para Python, solo dev; contraste, teclado, errores) | Al terminar |

---

*Estado: Fase 1 completa y decisiones aprobadas. La Fase 2a no ha comenzado; se espera la aprobación del mockup y de este plan.*

---

## 14. Ajuste de identidad visual (v5)

Tras revisar la maqueta v4, el usuario señaló que había perdido personalidad: las cuatro instituciones se veían como un mismo panel blanco con acento. Se conserva la estructura limpia (disposición, espaciado, estados, Inter, colores D1–D8) y se recupera, por institución, un **suelo de color**, una **geometría** y un **objeto firma**:

| Institución | Suelo | Geometría | Objeto firma |
|---|---|---|---|
| Hospital General `#0068FF` | Barra azul sólida, papel rayado de hoja de signos | Ortogonal, pestañas tipo carpeta, bordes finos | Encabezado del paciente como pulsera con dos orificios |
| Centro Pediátrico `#4D8687` | Papel milimetrado mantequilla, tinta verde azulada | Círculos, franjas diagonales, bordes gruesos, botones redondos | Burbujas con la edad (años y meses), franjas como curvas de crecimiento |
| Laboratorio `#A75FF1` | Violeta que se profundiza hacia abajo, placa de pocillos | Cuadrícula de círculos, esquinas contenidas | Etiqueta de muestra: franja de colores de tubos y código de barras derivado del ID |
| Clínica `#006977` | Fondo cálido pastel | Arcos concéntricos con los cuatro pasteles, formas suaves | Avatar con forma de corona, arcos en barra lateral y fondo |

Notas de implementación para la Fase 2b: el sistema compartido define por tema `--ink`, `--ground`, `--side`, `--border`, radios y un patrón de fondo; la barra lateral y el fondo toman esos tokens. Los adornos (burbujas, código de barras, arcos) son decorativos (`aria-hidden`) y no sustituyen ningún dato: la edad y el ID siguen en texto. En pantallas menores de 980 px se ocultan los adornos de la barra lateral. Verde azulado de la barra pediátrica: `#3A7172`, derivado de `#4D8687` para cumplir contraste con texto blanco. Se mantiene Inter como única tipografía (D, aprobado); si se quisiera una tipografía por institución habría que decidirlo aparte.
