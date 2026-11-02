# Contrato de la Clínica Odontológica con el frontend

Estado (31 de octubre de 2026): **el backend cubre todas las pantallas clínicas del mockup.**
Este documento dice qué llama cada pantalla de
[`referencia/Historiales identidad visual.html`](referencia/Historiales%20identidad%20visual.html),
escenarios «Clínica Odontológica · odontóloga» y «… · secretaria». Prefijo de todas las
rutas: `/api/v1`. El modelo en Firestore está en [modelo_odontologia.md](modelo_odontologia.md).

## Pantallas

| Pantalla del mockup | Quién la ve | Llamadas | Permiso |
| --- | --- | --- | --- |
| Iniciar sesión | Todos | `POST /auth/login`, `GET /auth/me` | — |
| Pacientes (buscador) | Odontólogo, secretaria | `GET /pacientes?nombre=&limite=` | `pacientes:leer` |
| Registrar paciente | Odontólogo, secretaria | `POST /pacientes` | `pacientes:registrar` |
| Ficha · Resumen | Odontólogo, secretaria | `GET /pacientes/{id}` | `pacientes:leer` |
| Editar datos | Odontólogo, secretaria | `PATCH /pacientes/{id}` | `pacientes:registrar` |
| Agregar alergias | Solo odontólogo | `POST /pacientes/{id}/alergias` | `pacientes:registrar` **y** `historiales:leer` |
| Ficha · Historial | Solo odontólogo | `GET /pacientes/{id}/historial?limite=&antes_de=` | `historiales:leer` |
| Nueva consulta | Solo odontólogo | `POST /pacientes/{id}/consultas` | `consultas:registrar` |
| Agregar adenda | Solo odontólogo | `POST /pacientes/{id}/consultas/{id_consulta}/adenda` | `consultas:registrar` |
| Ficha · Citas | Odontólogo, secretaria | `GET /pacientes/{id}/citas` | `citas:leer` |
| Ficha · Odontograma | Solo odontólogo | `GET /pacientes/{id}/odontograma`, `PUT /pacientes/{id}/odontograma/piezas/{pieza}` | `historiales:leer` / `consultas:registrar` |
| Archivar historial | Odontólogo con el permiso, **nunca** la secretaria | `POST /pacientes/{id}/archivo` | `historiales:archivar` |
| Agenda de citas | Odontólogo, secretaria | `GET /citas?desde=&hasta=&id_profesional=` | `citas:leer` |
| Agendar cita | Odontólogo, secretaria | `GET /citas/profesionales`, `POST /citas` | `citas:leer` y `citas:gestionar` |
| Actualizar estado de la cita | Odontólogo, secretaria | `POST /citas/{id}/estado` | `citas:gestionar` |

## Lo que calcula el cliente

El mockup muestra estos datos sin una ruta propia. Salen de las respuestas anteriores:

| Dato en pantalla | Cómo se obtiene |
| --- | --- |
| Piezas registradas | Número de elementos en `piezas` de `GET .../odontograma`. Solo vienen las piezas con estado. Puede pasar de 32 si hay temporales registradas. |
| Requieren atención | Piezas con estado `caries`, `fractura` o `extraccion_indicada`. |
| Última consulta | `consultas[0].fecha_hora` de `GET .../historial?limite=1`. |
| Próxima cita | La más cercana en el futuro con estado `programada` o `confirmada` de `GET .../citas`. |
| Citas en la semana, Hoy, Por atender, Canceladas | Conteos sobre `GET /citas` con `desde` y `hasta` de la semana. |
| Carga por profesional | Suma de `fin - inicio` por `id_profesional`, con los mismos datos. |
| Solo mis citas | `id_profesional` = `id_usuario` de `GET /auth/me`. |
| Nombre del profesional | `nombres` y `apellidos` de `GET /citas/profesionales`. Esa lista solo trae activos: para una cuenta dada de baja se usa la marca «Profesional ·1a2b» del mockup. |
| Cargar consultas anteriores | Enviar `siguiente_antes_de` como `antes_de`. Si llega `null`, no hay más. |

## Forma de las respuestas

```text
PacienteResponse   id_paciente, nombres, apellidos, fecha_nacimiento, archivado,
                   contacto { telefono, correo, direccion } | null,
                   alergias [ { sustancia, reaccion, severidad } ] | null
PacienteResumen    id_paciente, nombres, apellidos, fecha_nacimiento, archivado
ConsultaResponse   id_consulta, id_paciente, id_profesional, fecha_hora, motivo, notas,
                   diagnosticos [ { descripcion, codigo, sistema_codigo } ],
                   tratamientos [ { descripcion } ],
                   recetas [ { medicamento, dosis, frecuencia, via_administracion,
                               duracion_dias, instrucciones } ]
HistorialResponse  paciente, consultas, siguiente_antes_de
CitaResponse       id_cita, id_paciente, nombre_paciente, id_profesional, inicio, fin,
                   motivo, estado, creada_por, motivo_cambio
PiezaResponse      pieza, estado, superficies, nota, actualizado_por, actualizado_en
OdontogramaResp.   id_paciente, piezas [ PiezaResponse ]
Profesional agenda id_profesional, nombres, apellidos, rol, id_departamento
```

`alergias` tiene tres significados y la pantalla debe distinguirlos:

- `null`: no evaluadas, o quien consulta no tiene `historiales:leer`.
- `[]`: evaluadas, sin alergias conocidas.
- Lista con elementos: las alergias registradas.

## Valores y límites

Son los mismos del mockup. La API responde 422 fuera de ellos.

| Campo | Regla |
| --- | --- |
| `nombres`, `apellidos`, `sustancia` | 1 a 120 caracteres |
| `telefono` / `correo` / `direccion` | Hasta 30 / 254 / 300 |
| `reaccion` / `severidad` | Hasta 300 / 50 |
| `fecha_nacimiento` | No futura |
| Consulta: `motivo` / `notas` | 1 a 500 / hasta 5000 |
| Adenda: `nota` | Hasta 2000. Debe traer al menos un elemento. |
| `descripcion` de diagnóstico / de tratamiento | 1 a 500 / 1 a 1000 |
| `codigo`, `sistema_codigo` | Hasta 20 |
| `medicamento`, `dosis`, `frecuencia` | 1 a 200 |
| `via_administracion` / `instrucciones` | Hasta 100 / 1000 |
| `duracion_dias` | 1 a 3650 |
| Archivo: `motivo` | `traslado`, `fallecimiento` o `administrativo` |
| Archivo: `detalle` | Hasta 500 |
| Cita: `inicio` | Futuro y con zona horaria, p. ej. `2026-11-03T09:00:00-06:00` |
| Cita: `duracion_minutos` / `motivo` | 5 a 480 / 1 a 300 |
| Agenda: `desde`, `hasta` | Rango de hasta 31 días; devuelve como máximo 500 citas |
| Cita: `estado` | `programada → confirmada → atendida`; también `cancelada` o `no_asistio`. Los finales no cambian. |
| Pieza | FDI: 11–18, 21–28, 31–38, 41–48, 51–55, 61–65, 71–75, 81–85 (52 en total) |
| Pieza: `estado` | `sana`, `caries`, `obturada`, `corona`, `endodoncia`, `sellante`, `fractura`, `protesis`, `implante`, `extraccion_indicada`, `ausente`, `en_erupcion` |
| Pieza: `superficies` | `oclusal`, `incisal`, `mesial`, `distal`, `vestibular`, `lingual`, `palatino`. Vacío significa toda la pieza. |
| Pieza: `nota` | Hasta 500 |

## Errores que debe contemplar cada pantalla

| Código | Caso en la clínica | Qué hace el mockup |
| --- | --- | --- |
| 401 | Sesión vencida o revocada | Vuelve al login y conserva la pantalla. |
| 403 | Falta el permiso. La secretaria lo recibe en historial, odontograma, consultas, archivo y `POST .../alergias`. | Esas opciones ya no se muestran. |
| 404 | Paciente, consulta o cita inexistente | Estado vacío. |
| 409 | Historial archivado, horario ocupado, estado final de una cita o baja repetida | Muestra el mensaje de la API. |
| 422 | Dato inválido; cancelar sin motivo; marcar `atendida` o `no_asistio` antes de la hora; profesional inactivo o que no atiende | Marca el campo o muestra el mensaje. |
| 503 | Firestore no responde o hay demasiadas operaciones simultáneas sobre el mismo dato | Pantalla «intenta de nuevo». |

## Diferencias con lo que dice el mockup

El mockup no se modificó. Estas notas suyas quedaron atrasadas respecto al backend y el
frontend debe seguir este documento:

| Mockup | Backend | Qué debe hacer el frontend |
| --- | --- | --- |
| Nota «D5»: la secretaria no puede agendar porque no hay lista de profesionales. | `GET /citas/profesionales` ya existe. | Mostrar «Agendar cita» a quien tenga `citas:gestionar` y ofrecer un selector de profesional. La secretaria no aparece en la lista porque no atiende. |
| El profesional de la cita es siempre «Tú (sesión actual)». | `POST /citas` acepta cualquier profesional activo que atienda. | Preseleccionar la sesión si atiende pacientes. |
| Los profesionales se ven como «Profesional ·1a2b». | Hay nombres para los activos. | Usar el nombre y dejar esa marca para cuentas de baja. |
| El modal de estado ofrece atendida, no asistió y cancelada. | También acepta `confirmada`. | Opcional: agregar «Confirmar». |

## Administración

Las pantallas del escenario «Clínica Odontológica · administración» (Resumen, Usuarios y
accesos, Bitácora) usan las rutas de `/profesionales`, que llegaron con `Develop` junto con sus
pantallas en `js/vistas/admin/`.
