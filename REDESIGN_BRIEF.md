# REDESIGN_BRIEF.md

## Historiales — Dirección visual y guía de reestructuración del frontend

**Estado:** brief inicial aprobado para auditoría y planificación.  
**Alcance:** rediseño de presentación del frontend.  
**Principio rector:** mejorar sustancialmente la experiencia visual sin modificar la arquitectura ni el comportamiento del backend.

---

## 1. Contexto del proyecto

Historiales es una plataforma compartida por cuatro instituciones médicas independientes:

- Hospital General.
- Centro Pediátrico.
- Laboratorio Clínico.
- Clínica Odontológica.

Cada institución tiene necesidades y flujos de trabajo distintos, pero las cuatro forman parte de una misma plataforma. La solución debe transmitir esa unidad sin borrar la personalidad de cada institución.

El objetivo del rediseño es conseguir una interfaz contemporánea, profesional, clara y agradable de utilizar. No se busca convertir el producto en una landing page ni en una demostración visual desconectada de sus funciones reales.

El proyecto se evalúa principalmente por su implementación de backend y bases de datos. Sin embargo, el frontend también debe tener una presentación cuidada, coherente y suficientemente pulida para una demostración académica.

## 2. Objetivo y alcance

### Sí se debe hacer

- Rediseñar la presentación visual del frontend.
- Mejorar jerarquía visual, tipografía, espaciado, color, navegación, tablas, formularios, tarjetas, estados y feedback.
- Unificar los elementos compartidos cuando eso reduzca duplicación y mejore el mantenimiento.
- Mantener características particulares de cada institución cuando respondan a sus tareas reales.
- Adaptar la propuesta visual existente a la arquitectura real del repositorio, si resulta conveniente.
- Mejorar el comportamiento en escritorio y conservar una adaptación responsive funcional.

### No se debe hacer

- No rediseñar ni reestructurar el backend.
- No cambiar motores, conexiones, modelos, esquemas, migraciones ni repositorios de datos.
- No cambiar contratos, rutas, métodos, parámetros ni respuestas de los endpoints existentes.
- No modificar autenticación, autorización, roles o permisos.
- No cambiar reglas de negocio ni validaciones funcionales.
- No reemplazar datos reales de la API por datos simulados para facilitar el diseño.
- No eliminar funcionalidades existentes para simplificar la interfaz.
- No introducir un framework, dependencia o proceso de compilación nuevo sin justificar primero su necesidad.

Si durante la auditoría se descubre que un ajuste visual requiere un cambio de backend, no implementarlo silenciosamente: documentar el motivo y solicitar aprobación.

## 3. Estado de la propuesta HTML existente

Existe un archivo HTML independiente titulado **Identidad visual Historiales.html**. Fue generado como mockup exploratorio y todavía no ha sido aprobado ni integrado al producto.

Debe tratarse como **referencia visual y fuente de ideas**, no como fuente de verdad de la arquitectura ni como implementación autorizada.

Antes de reutilizar código, inspeccionar el frontend real del repositorio y comparar:

- Qué pantallas y componentes del mockup ya existen en el producto.
- Qué ideas visuales merece la pena conservar.
- Qué interacciones del mockup son solamente demostrativas.
- Qué contenido o datos son sintéticos.
- Qué partes pertenecen al panel de revisión de la propuesta y no al producto.

### Atención: controles del mockup

La barra superior que permite cambiar entre Login, instituciones, estados de datos y roles es una herramienta de revisión del mockup. No debe asumirse que forma parte de la interfaz de producción. No incorporarla al producto salvo que se compruebe que existe una necesidad funcional equivalente.

El mockup contiene datos y comportamientos de demostración. No copiarlos como si fueran datos reales ni sustituir con ellos la integración actual con la API.

## 4. Dirección artística general

### Concepto

**Modern Clinical SaaS / Clinical Modernism.**

La interfaz debe sentirse como software profesional de gestión clínica actual: ordenado, confiable, legible y eficiente. Evitar tanto la apariencia de software antiguo como el aspecto excesivamente genérico de una plantilla de dashboard.

### Principios visuales

1. La información clínica debe tener prioridad sobre la decoración.
2. La mayor parte de la interfaz debe utilizar superficies neutras.
3. Los colores institucionales deben funcionar como acentos de identidad, no como grandes bloques saturados que compitan con la información.
4. La navegación y los componentes comunes deben ser consistentes entre instituciones.
5. Las particularidades visuales deben apoyar los flujos reales de cada institución.
6. Utilizar espacio en blanco, agrupación y jerarquía tipográfica para reducir ruido visual.
7. Evitar bordes negros gruesos, radios excesivamente diferentes entre instituciones, sombras duras, degradados omnipresentes y combinaciones de colores primarios muy saturados.

### Proporción de color orientativa

Como punto de partida, utilizar aproximadamente:

- 75–80 % superficies neutras.
- 15–20 % superficies secundarias, separadores y elementos de apoyo.
- Hasta 5 % de acentos institucionales intensos.

No es una regla rígida: ajustar según la pantalla y verificar que el contenido siga siendo el protagonista.

## 5. Sistema visual compartido

### Colores globales iniciales

Estos valores son la base neutral propuesta para la plataforma. No es necesario forzar un color de marca global adicional: el logotipo actual ya comunica la identidad conjunta y cada institución tiene su propio color principal. Se pueden ajustar ligeramente después de revisar contraste, pero no cambiar sin una razón documentada.

| Token | Valor | Uso |
|---|---|---|
| `--app-bg` | `#F4F7FA` | Fondo general |
| `--surface` | `#FFFFFF` | Tarjetas, paneles, formularios |
| `--text-primary` | `#172B3A` | Texto principal |
| `--text-secondary` | `#64748B` | Texto secundario y metadatos |
| `--border` | `#DCE5EC` | Bordes y separadores |

### Tipografía

- Familia principal: **Inter**.
- Títulos: pesos 600–700.
- Texto de interfaz: pesos 400–500.
- Etiquetas y controles: peso 500–600 según jerarquía.
- Usar tamaños y alturas de línea consistentes.
- Cifras clínicas, fechas, horas e identificadores deben ser fáciles de comparar y escanear.

No asignar una familia tipográfica diferente a cada institución. La identidad se construye principalmente con color, jerarquía, iconografía y componentes especializados.

### Componentes y geometría

Valores iniciales orientativos:

- Bordes: 1 px, tono neutral.
- Tarjetas y paneles: radio de 12–16 px.
- Inputs: radio de 8–10 px.
- Botones: radio aproximado de 9–10 px.
- Controles interactivos: altura suficiente para operarse cómodamente.
- Sombras: discretas, reservadas principalmente para modales, menús flotantes y niveles de elevación.

Crear componentes visuales compartidos para botones, campos, etiquetas de estado, tarjetas, tablas, pestañas, modales, drawers, mensajes y estados vacíos, siempre que la arquitectura actual lo permita.

### Iconografía

Mantener la solución de iconografía que ya utilice el proyecto si es coherente. Si ya está integrada Lucide, conservarla. No agregar otra biblioteca únicamente por preferencia estética. Los iconos deben ser consistentes en grosor, tamaño y alineación.

## 6. Identidad de las instituciones

Los siguientes colores principales están aprobados como dirección de diseño. Deben aplicarse mediante variables o temas institucionales, no mediante colores dispersos y hardcodeados por toda la hoja de estilos.

### 6.1 Hospital General

**Color principal aprobado: `#0068FF`**  
Personalidad: clínico, preciso, confiable y operativo.

Dirección visual:

- Interfaz sobria, clara y estructurada.
- Usar el azul para navegación activa, acciones principales, enlaces y pequeños indicadores.
- Evitar que toda la barra lateral o grandes paneles sean azul intenso.
- Dar prioridad a la lectura de pacientes, citas, diagnósticos, tratamientos y registros.
- Mantener una jerarquía clara para información crítica.

#### Semántica de estados clínicos y operativos

Los colores de estado deben ser universales y no confundirse con el color institucional.

- **Emergencia/crítico:** rojo fuerte, por ejemplo `#DC2626`.
- **Grave/urgente:** naranja o ámbar visible, por ejemplo `#F59E0B` o `#EA580C`.
- **Advertencia:** tono ámbar diferenciado, de acuerdo con el contexto.
- **Correcto/completado:** verde con contraste suficiente.
- **Neutral/en espera:** grises o azul tenue.

No comunicar gravedad únicamente mediante color: acompañar los indicadores con texto, icono o etiquetas. Comprobar que rojo, naranja y verde no se utilicen de forma ambigua en módulos distintos.

### 6.2 Centro Pediátrico

**Color principal aprobado como base: `#4D8687`**  
Personalidad buscada: cercana, cálida, optimista y profesional; no infantilizada.

El color base todavía necesita una identidad secundaria con más personalidad. Explorar una combinación contenida de tonos cálidos y pasteles —por ejemplo, coral suave, amarillo mantequilla y menta clara— que complemente el verde azulado.

Dirección visual:

- Transmitir seguimiento, crecimiento y cuidado continuo.
- Dar protagonismo a las líneas de tiempo, controles de crecimiento, percentiles y vacunación.
- Los gráficos de crecimiento deben ser claros y utilizar colores consistentes.
- Se puede introducir una pequeña calidez visual mediante acentos, ilustraciones abstractas o detalles de componentes, sin convertir toda la pantalla en una interfaz infantil.
- No usar una cuadrícula decorativa detrás de grandes cantidades de texto.

**Pendiente de aprobación:** proponer una paleta secundaria de 2–3 colores complementarios y mostrar cómo convive con `#4D8687` antes de fijarla como definitiva.

### 6.3 Laboratorio Clínico

**Color principal aprobado: `#A75FF1`**  
Personalidad: analítica, técnica, precisa y contemporánea.

Dirección visual:

- Se permiten degradados discretos derivados del violeta, por ejemplo entre `#A75FF1` y un violeta más profundo.
- Reservar degradados para acentos, encabezados pequeños, indicadores o visualizaciones; no aplicarlos indiscriminadamente a fondos de lectura.
- Priorizar tablas, resultados, muestras, órdenes, trazabilidad y estados del procesamiento.
- Mantener una alta legibilidad y una densidad de información controlada.
- Los colores específicos de tubos, muestras o categorías de análisis deben conservar su significado funcional y no confundirse con el color de marca.

### 6.4 Clínica Odontológica

**Color principal aprobado: `#006977`**  
Personalidad: limpia, contemporánea, tranquila y profesional.

Dirección visual:

- Esta institución es una de las identidades visuales preferidas y debe conservar el carácter estético de la propuesta que motivó su aprobación.
- Utilizar el verde azulado como color de marca, navegación activa y acciones principales.
- Complementarlo con tonos pastel que generen contraste agradable y aporten calidez.
- Mantener una interfaz especialmente práctica para recepción y secretaría.
- La agenda y el odontograma deben tener jerarquía visual clara y ser rápidos de operar.

**Nota sobre un color de referencia:** se recibió el valor `#f5722`, pero no es un código hexadecimal CSS válido porque tiene una longitud incorrecta. No utilizarlo literalmente ni adivinar su valor. Proponer tonos pastel compatibles con `#006977` y dejar la selección final sujeta a aprobación.

## 7. Login e identidad global

- Conservar inicialmente el logotipo actual de Historiales y su símbolo de cuatro cuadrados.
- El login debe ser neutral: la institución se conoce a partir de la cuenta autenticada, no por una selección libre de la persona que inicia sesión.
- Presentar una sola plataforma con cuatro identidades conectadas.
- Evitar cuatro bloques enormes de colores saturados.
- Preferir un formulario claro y una composición secundaria más sutil que represente las cuatro instituciones.
- Mantener los estados de error, bloqueo, carga y sesión vencida claramente diferenciados.
- No revelar información sensible ni confirmar innecesariamente si una cuenta existe.

## 8. Experiencia, dispositivos y movimiento

### Prioridad de escritorio

La interfaz está destinada principalmente a un software de escritorio. Optimizar primero para pantallas de escritorio y flujos de trabajo con tablas, formularios, agendas y expedientes.

Conservar soporte responsive para tabletas y móviles, pero no sacrificar la experiencia de escritorio para imitar el diseño de una aplicación móvil.

En pantallas estrechas:

- Evitar que tablas o formularios rompan el layout.
- Utilizar scroll horizontal controlado cuando sea necesario.
- Reorganizar navegación y paneles de forma predecible.
- Mantener acciones principales accesibles.

### Tema oscuro

No implementar modo oscuro en esta fase. Dejar la arquitectura visual suficientemente ordenada para que pueda añadirse después, sin invertir ahora tiempo en mantener dos temas.

### Animaciones

Nivel deseado: **intermedio y funcional**.

Se esperan:

- Transiciones discretas de hover, focus y selección.
- Feedback visual para acciones, guardados y errores.
- Apertura y cierre cuidados de modales y drawers.
- Transiciones entre vistas cuando realmente ayuden a orientar al usuario.
- Estados de carga y progreso claros.

Evitar animaciones decorativas constantes o que retrasen acciones. Respetar `prefers-reduced-motion`.

## 9. Arquitectura frontend y despliegue

La propuesta visual es independiente y todavía no está aprobada. El repositorio real es la fuente de verdad.

### Node.js

La decisión actual es **evitar depender de Node.js en producción**, no necesariamente eliminarlo del desarrollo.

- Si el frontend actual usa un proceso de build, inspeccionarlo antes de proponer cambios.
- Node puede utilizarse durante desarrollo o compilación si la arquitectura existente lo necesita.
- El despliegue no debe requerir un proceso Node activo si el resultado puede servirse como archivos estáticos.
- FastAPI puede servir archivos estáticos y, si corresponde al diseño actual del proyecto, plantillas HTML.
- No migrar a React, Vite, Jinja2 u otra tecnología solo por modernizar el aspecto. Primero auditar qué existe y justificar cualquier cambio.
- No crear un frontend paralelo que duplique la aplicación actual.

La prioridad es mantener la integración existente con FastAPI y la API, con el menor cambio técnico posible.

## 10. Reglas de integración y preservación funcional

Antes de cambiar cualquier pantalla, identificar:

- Qué endpoint alimenta cada vista.
- Qué permisos determinan la visibilidad de cada acción.
- Qué formularios tienen validaciones y reglas específicas.
- Qué estados de carga, error, vacío y éxito existen.
- Qué rutas y enlaces internos se utilizan.
- Qué comportamiento depende de cada institución y rol.

Durante la implementación:

1. Conservar los endpoints y contratos existentes.
2. Conservar los nombres, formatos y flujos de datos que consume el frontend.
3. No inventar datos para llenar espacios visuales.
4. No mostrar acciones que el usuario no tenga permiso de ejecutar.
5. No eliminar mensajes de error ni validaciones para simplificar la interfaz.
6. Mantener accesibles los controles por teclado y con indicadores de foco visibles.
7. Mantener contraste suficiente para texto, iconos y estados.
8. No depender exclusivamente del color para explicar alertas o estados.

## 11. Metodología de trabajo por fases

### Fase 1 — Auditoría del repositorio (solo lectura)

Antes de implementar:

- Inspeccionar la estructura real del repositorio.
- Identificar framework, templates, CSS, JavaScript, dependencias y proceso de build.
- Identificar cómo FastAPI entrega actualmente el frontend.
- Identificar rutas, vistas, roles, permisos y endpoints consumidos.
- Identificar pruebas y comandos existentes para validar el proyecto.
- Comparar la aplicación real con el mockup independiente.
- Registrar qué elementos del mockup son aprovechables y cuáles son solo demostrativos.

**Entregable:** crear `REDESIGN_AUDIT.md` con el estado real del frontend, dependencias, puntos de entrada, integración con FastAPI, riesgos y propuesta de implementación.

**No modificar código durante esta fase.** Al terminar, presentar hallazgos y plan para revisión.

### Fase 2 — Sistema visual compartido

Después de aprobar el plan:

- Definir tokens globales y temas institucionales.
- Establecer tipografía, escala de espaciado, radios, bordes, sombras y estados.
- Construir o adaptar componentes compartidos en la arquitectura existente.
- Verificar que las cuatro instituciones puedan usar la misma base sin duplicar pantallas completas innecesariamente.

### Fase 3 — Rediseño institucional gradual

Implementar y validar una institución a la vez, en este orden inicial:

1. **Clínica Odontológica:** primera prioridad visual; conservar la dirección estética aprobada.
2. **Hospital General:** aplicar `#0068FF`, con alertas críticas rojas y estados graves naranjas/ámbar.
3. **Laboratorio Clínico:** aplicar `#A75FF1` y degradados discretos.
4. **Centro Pediátrico:** finalizar la identidad complementaria después de presentar y aprobar sus tonos secundarios.

Después de cada institución, verificar navegación, componentes, permisos y flujos antes de avanzar.

### Fase 4 — Validación global

Comprobar:

- Que las cuatro instituciones comparten una experiencia coherente.
- Que la identidad de cada una se reconoce sin saturar la interfaz.
- Que funcionan login, navegación, formularios, tablas, modales, drawers y estados.
- Que se mantienen roles y permisos.
- Que no se han modificado endpoints ni comportamiento del backend.
- Que el frontend funciona con el mecanismo de despliegue actual y no requiere un proceso Node en producción.
- Que no hay errores de consola, recursos faltantes ni problemas graves de responsive.
- Que los estados de error, vacío, carga y éxito se siguen mostrando correctamente.

Registrar las pruebas realizadas y cualquier limitación pendiente.

## 12. Criterio para tomar decisiones

Cuando exista más de una solución posible, elegir en este orden:

1. Preservar la arquitectura y las funcionalidades existentes.
2. Favorecer legibilidad, rapidez y prevención de errores.
3. Reutilizar componentes y estilos compartidos cuando tenga sentido.
4. Mantener la identidad institucional aprobada.
5. Evitar dependencias y complejidad que no aporten valor claro.

No interpretar este brief como autorización para reescribir toda la aplicación. Es una guía para auditar, planificar y luego mejorar exclusivamente su presentación visual.

---

## 13. Instrucción inicial para Claude

Lee este documento completo y realiza únicamente la **Fase 1 — Auditoría del repositorio**.

No implementes cambios todavía. No modifiques backend, frontend, dependencias ni configuración durante la auditoría.

Inspecciona el repositorio real y contrasta su estructura con el mockup independiente `Identidad visual Historiales.html`, si está disponible. No asumas que el mockup representa la arquitectura actual ni que sus datos de ejemplo son datos reales.

Crea `REDESIGN_AUDIT.md` con hallazgos verificables y una propuesta de ejecución que respete este brief. Señala expresamente cualquier conflicto entre el brief y la arquitectura encontrada, y cualquier decisión que requiera aprobación.

Al terminar, resume:

- Cómo está construido y servido el frontend actualmente.
- Qué puede conservarse y reutilizarse.
- Qué partes conviene rediseñar o reorganizar.
- Cómo mantener FastAPI y evitar Node.js en producción.
- Qué riesgos existen para la integración con la API.
- En qué orden implementarías los cambios.

Espera aprobación antes de comenzar la implementación.
