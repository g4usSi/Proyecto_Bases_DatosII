# Frontend: decisión y plan de trabajo

Estado (3 de noviembre de 2026): **la interfaz existe en `app/presentation/web/`** y se sirve en
`/app/` desde la misma API, sin Node ni compilación. Incluye acceso, cambio obligatorio de
contraseña, la administración completa (superusuario y administrador de cada entidad) y, en
esta versión, las pantallas de la Clinica Odontologica y del Centro Pediatrico
(`js/modulos/clinica.js` y `js/modulos/pediatrico.js`). Las
de las demás instituciones se agregan como módulos en su rama. El mockup sigue
siendo la referencia visual: `docs/referencia/Historiales identidad visual.html`. Los contratos
están en [la guía del frontend](api_frontend_hospital_laboratorio.md). El plan que sigue es histórico.

## Centro Pediátrico

Pacientes, ficha con edad en burbujas, historial, crecimiento, vacunación, tutores, agenda,
catálogo de vacunas y facturación. Cada pantalla aparece según los permisos de la cuenta.

- **Lo que el mockup propone y no se construyó:** «Lotes y vencimientos». El equipo decidió no
  controlar lotes ni existencias (migración `010`) y la API no los expone.
- **Facturación distinta del Hospital:** una factura por consulta, a nombre de un tutor; pagada
  significa saldo cero; se anula solo sin pagos. No hay cierre, anulación de pagos, catálogo de
  servicios ni pago con cheque. El mockup llama «Emitida» a lo que la API llama `abierto`; se
  muestra como «Por cobrar». El resumen no da «facturado esta semana»: se muestra «cobrado hoy».
- **La base debe tener las migraciones `006` a `016`**, y `nombre_vacuna` no se carga con ninguna:
  sin datos en esa tabla, Vacunación avisa que el catálogo está vacío.

## Cómo está construida

- **Agregar pantallas:** cada institución declara un módulo con `registrarModulo` en
  `js/modulos/` (a quién aplica, menú y vistas) y se importa en `js/main.js`. El marco, el tema
  y la sesión no se tocan. Una cuenta sin módulo ve un aviso, no una pantalla rota.
- **Cristal para el marco, papel para el dato:** barra lateral, barra superior y diálogos usan
  `backdrop-filter`; tablas y formularios van sobre superficies casi opacas (`--papel`). Con
  `prefers-reduced-transparency` o sin soporte de desenfoque, todo pasa a superficies sólidas.
- **Temas:** `data-tema` fija el color, la geometría y el suelo de cada institución en
  `css/tokens.css`. El suelo es fijo y estático para que el desenfoque no se recalcule al desplazar.
- **Recursos locales:** Inter (OFL) y un sprite de Lucide (ISC, generado con los SVG de
  `lucide-static` 0.460.0) están en `assets/` con sus licencias.
- **CSP:** va en un `<meta>`, así que no aplican `frame-ancestors` ni `report-uri`; si se
  necesitan, hay que enviarla como cabecera desde el servidor. Prohíbe estilos en línea: los
  valores dinámicos se asignan con `style.setProperty`.
- **Sesión:** el token vive en `sessionStorage` y dura 30 minutos sin renovación; se avisa
  5 minutos antes y, al vencer, se vuelve a la misma pantalla tras iniciar sesión.
- **Límite conocido:** el detalle de la bitácora guarda el ID del área, no su nombre.

Estado (23 de octubre de 2026): **tecnología decidida, nada construido**. Faltan los
mockups; este documento deja listo qué debe tener cada pantalla para diseñarlos y
después programarlos sin volver a discutir lo básico.

## Decisión del equipo

HTML, CSS y JavaScript sencillos, **servidos por la misma aplicación FastAPI**, sin
paso de compilación (sin Node, sin `npm`). La API ya expone todo lo necesario en
`/docs`; el cliente solo la consume.

### ¿HTML/JS o React? Recomendación: HTML/JS

Con las decisiones tomadas, recomendamos HTML/JS sencillo (módulos ES nativos):

| Criterio | HTML/JS servido por FastAPI | React |
| --- | --- | --- |
| Arranque | Una carpeta de archivos estáticos. `uvicorn` ya la sirve. | Node, `npm`, Vite, una etapa de compilación y otra en el Dockerfile. |
| Mismo origen que la API | Sí: sin CORS, sin segundo puerto, sin segundo contenedor. | No: se sirve aparte (o hay que configurar un proxy). |
| Dos integrantes, tiempo corto | Menos piezas que aprender y que se rompan. | Más herramientas por entender antes de mostrar la primera pantalla. |
| Odontograma interactivo | Suficiente: 52 piezas como `<g>` de un SVG, un clic abre un panel y se llama a `PUT`. | Más cómodo si el odontograma creciera (deshacer, varias piezas a la vez). |
| Estado compartido entre pantallas | Poco: sesión y paciente actual. Alcanza con un módulo. | Es donde React más ayuda; aquí casi no hace falta. |
| Pantallas | ~8, formularios y tablas. | Se justifica con muchas más pantallas o equipos grandes. |
| Seguridad | Sin dependencias externas que auditar; se usa `textContent`. | Cientos de paquetes transitivos que revisar. |

**Cuándo cambiar a React:** si el equipo ya lo domina bien, o si el odontograma pasa de
"clic y elegir estado" a edición compleja (deshacer, arrastrar, comparar versiones).
Como el cliente solo habla con la API por HTTP, cambiar después no obliga a tocar el
backend.

## Cómo se sirve desde FastAPI

Carpeta propuesta `app/presentation/web/` y montaje en `/app` con `StaticFiles`
(`html=True`). Todavía no existe.

```text
app/presentation/web/
  index.html                 Contenedor y menú
  css/estilos.css
  js/api.js                  fetch con el token; traduce 401/403/404/409/422/501/503
  js/sesion.js               login, /auth/me, logout, permisos vigentes
  js/vistas/                 una por pantalla: pacientes.js, historial.js, citas.js ...
  js/odontograma.js          SVG y panel de la pieza
```

Mismo origen que la API: no hace falta CORS. Si más adelante se separa, hay que
configurar `HISTORIALES_CORS_ORIGINS`.

## Qué pide el PDF

- Iniciar sesión y ver la información de forma ordenada.
- **La interfaz no cambia según el motor.** Las secciones solo aparecen o
  desaparecen por *capacidad* (permiso del usuario y si su institución la ofrece), nunca
  por el nombre del motor.
- Registrar pacientes, agregar consultas con diagnósticos, tratamientos y recetas, y
  archivar historiales.
- Para la clínica: agenda de citas y odontograma.

## Pantallas y permisos

La sesión trae `permisos` en `GET /api/v1/auth/me`. Ocultar un botón **no sustituye**
la autorización: la API vuelve a validar cada llamada.

| Pantalla | Quién la ve | Rutas | Permiso |
| --- | --- | --- | --- |
| Login | Todos | `POST /auth/login`, `GET /auth/me` | — |
| Registrar paciente | Quien registra (secretaria incluida) | `POST /pacientes` | `pacientes:registrar` |
| Buscar paciente | Quien lee pacientes | `GET /pacientes?nombre=` | `pacientes:leer` |
| Ficha del paciente | Quien lee pacientes | `GET /pacientes/{id}` | `pacientes:leer` |
| Historial de consultas | Personal clínico | `GET /pacientes/{id}/historial` | `historiales:leer` |
| Nueva consulta (diagnóstico, tratamiento, receta) | Personal clínico | `POST /pacientes/{id}/consultas` | `consultas:registrar` |
| Archivar historial (baja) | Personal clínico con permiso. **Nunca la secretaria.** | `POST /pacientes/{id}/archivo` | `historiales:archivar` |
| Agenda de citas | Clínica odontológica | `GET /citas`, `POST /citas`, `POST /citas/{id}/estado` | `citas:leer` / `citas:gestionar` |
| Citas del paciente | Clínica odontológica | `GET /pacientes/{id}/citas` | `citas:leer` |
| Odontograma | Odontólogo (clínico) | `GET`/`PUT /pacientes/{id}/odontograma...` | `historiales:leer` / `consultas:registrar` |

### Reglas de interfaz que salen de las decisiones

- **Secretaria** (solo clínica odontológica): ve registrar paciente, ficha y agenda.
  No hay pestañas de historial ni odontograma, ni botón de archivar.
- **Alergias, campo opcional.** El formulario de registro las deja vacías por defecto.
  Hay tres situaciones distintas y la pantalla debe distinguirlas:
  - sin enviar `alergias` → "no registradas" (no se preguntó);
  - `alergias: []` → "sin alergias conocidas" (se preguntó y no tiene);
  - lista con elementos → mostrarlas.
  La secretaria **puede** anotarlas al registrar, pero la API no se las devuelve después
  (llegan como `null`) y responde 403 si intenta agregar más con `POST .../alergias`. La
  pantalla de quien no tiene `historiales:leer` no debe decir "no registradas": muestra
  el aviso de información reservada, como el mockup.
- **Contacto** también es opcional (teléfono, correo, dirección).
- **501**: mostrar "Esta función todavía no está disponible para tu institución". Hoy solo
  lo devuelven los módulos propios de una institución fuera de ella, como el odontograma
  (los demás flujos funcionan en los cuatro motores).
  **503**: "El servicio de datos no está disponible, intenta más tarde".
- **401**: volver al login. **409**: historial archivado u horario ocupado, con el
  mensaje de la API. **422**: marcar el campo.

### Búsqueda de pacientes

`GET /api/v1/pacientes?nombre=...&limite=20` (permiso `pacientes:leer`) ya existe y
funciona igual en los cuatro motores: cada palabra escrita debe ser el comienzo de una
palabra del nombre, sin importar mayúsculas ni acentos. Pide al menos 2 letras y devuelve
un resumen (`id_paciente`, nombres, apellidos, fecha de nacimiento y `archivado`) que debe
marcarse en la lista para no ofrecer "nueva consulta" a un historial archivado. Para el
detalle (contacto, alergias) se llama luego a `GET /pacientes/{id}`.

## Odontograma interactivo

Numeración FDI / ISO 3950: permanentes 11–18, 21–28, 31–38, 41–48; temporales 51–55,
61–65, 71–75, 81–85. Total máximo: 52 piezas.

```text
Superior   18 17 16 15 14 13 12 11 | 21 22 23 24 25 26 27 28
Temporales       55 54 53 52 51 | 61 62 63 64 65
Temporales       85 84 83 82 81 | 71 72 73 74 75
Inferior   48 47 46 45 44 43 42 41 | 31 32 33 34 35 36 37 38
```

### Estados: lista fija (decisión del equipo)

La API **rechaza con 422** cualquier valor fuera de esta lista (en minúsculas, con
guion bajo). Está definida en `EstadoDental` de `app/domain/odontograma.py`; para
agregar uno basta sumarlo ahí y en la tabla de abajo.

| Valor de la API | Etiqueta | Marca sugerida |
| --- | --- | --- |
| `sana` | Sana | Verde, sin símbolo |
| `caries` | Caries | Rojo, "C" |
| `obturada` | Obturada | Azul, "O" |
| `corona` | Corona | Dorado, "Co" |
| `endodoncia` | Endodoncia | Morado, "E" |
| `sellante` | Sellante | Celeste, "S" |
| `fractura` | Fractura | Naranja, "F" |
| `protesis` | Prótesis | Gris azulado, "P" |
| `implante` | Implante | Gris oscuro, "I" |
| `extraccion_indicada` | Extracción indicada | Rojo con tachado, "X" |
| `ausente` | Ausente | Gris claro, "—" |
| `en_erupcion` | En erupción | Amarillo, "↑" |

Las marcas sugeridas son solo una propuesta para los mockups. **El color nunca debe ser
el único indicador** (daltonismo): cada estado lleva además su letra o símbolo.

Superficies que se pueden marcar en una pieza: `oclusal`, `incisal`, `mesial`, `distal`,
`vestibular`, `lingual`, `palatino`. Una pieza admite además una nota de hasta 500
caracteres.

### Flujo

1. `GET /pacientes/{id}/odontograma` devuelve solo las piezas con estado. Las demás se
   pintan como "sin registrar" (distinto de `sana`).
2. Clic o `Enter` sobre una pieza abre un panel con estado, superficies y nota.
3. Guardar llama a `PUT /pacientes/{id}/odontograma/piezas/{pieza}`; al responder 200 se
   repinta esa pieza. 409 si el historial está archivado.
4. Cada pieza debe ser alcanzable con teclado y tener texto accesible ("Pieza 36, caries").

## Sesión y seguridad del cliente

- El token dura 30 minutos. Guardarlo en memoria o `sessionStorage`; **no** en
  `localStorage`. Al cerrar sesión llamar `POST /auth/logout`.
- Escribir datos de la API con `textContent`, nunca con `innerHTML`: nombres, notas y
  recetas son texto de usuarios.
- No cargar scripts de CDN: todo local, para poder usar una política
  `Content-Security-Policy: default-src 'self'`.
- Datos de demostración siempre sintéticos.

## Mockups

Cubiertos en `referencia/Historiales identidad visual.html`, con qué rol ve cada pantalla, sus
errores y su estado vacío.

- [x] Login
- [x] Menú principal según rol (secretaria / odontólogo / otros)
- [x] Registrar paciente (con contacto y alergias opcionales; el Centro Pediátrico exige fecha de nacimiento)
- [x] Buscar paciente por nombre (lista con marca de archivado)
- [x] Ficha del paciente
- [x] Historial de consultas
- [x] Nueva consulta con varios diagnósticos, tratamientos y recetas
- [x] Archivar historial (motivo y detalle)
- [x] Agenda de citas (semana) y nueva cita
- [x] Odontograma interactivo con panel de pieza

## Orden de trabajo sugerido

1. ~~Mockups de las pantallas anteriores.~~ Hecho.
2. Esqueleto: montaje de `/app`, login, `/auth/me`, menú por permisos, manejo de errores.
3. Pacientes: registrar y ficha.
4. Historial y nueva consulta.
5. Agenda de citas.
6. Odontograma.
7. Revisión de accesibilidad, estados vacíos y mensajes 501/503.
