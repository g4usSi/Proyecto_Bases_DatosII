# Frontend: decisión y plan de trabajo

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
  (llegan como `null`). La pantalla de quien no tiene `historiales:leer` no debe decir
  "no registradas": simplemente no muestra esa sección.
- **Contacto** también es opcional (teléfono, correo, dirección).
- **501**: mostrar "Esta función todavía no está disponible para tu institución". Hoy solo
  lo devuelven citas y odontograma fuera de la clínica odontológica (los demás flujos
  funcionan en los cuatro motores).
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

## Mockups pendientes

Cada mockup debe indicar: qué rol lo ve, qué pasa con 403/501/503 y el estado vacío.

- [ ] Login
- [ ] Menú principal según rol (secretaria / odontólogo / otros)
- [ ] Registrar paciente (con contacto y alergias opcionales; el Centro Pediátrico exige fecha de nacimiento)
- [ ] Buscar paciente por nombre (lista con marca de archivado)
- [ ] Ficha del paciente
- [ ] Historial de consultas
- [ ] Nueva consulta con varios diagnósticos, tratamientos y recetas
- [ ] Archivar historial (motivo y detalle)
- [ ] Agenda de citas (día o semana) y nueva cita
- [ ] Odontograma interactivo con panel de pieza

## Orden de trabajo sugerido

1. Mockups de las pantallas anteriores.
2. Esqueleto: montaje de `/app`, login, `/auth/me`, menú por permisos, manejo de errores.
3. Pacientes: registrar y ficha.
4. Historial y nueva consulta.
5. Agenda de citas.
6. Odontograma.
7. Revisión de accesibilidad, estados vacíos y mensajes 501/503.
