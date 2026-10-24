# Clínica Odontológica en Cloud Firestore: modelo documental

Estado (23 de octubre de 2026): modelo implementado y probado contra el proyecto
`proyectobases2-83f2e`, base `(default)`. Código en
`app/infrastructure/persistence/firestore/unidad.py`; pruebas reales en
`tests/integration/test_firestore.py` (crean y borran datos sintéticos).

Decisiones del equipo aplicadas:

- Cada institución guarda solo sus propios pacientes. `contacto` y `alergias` son
  opcionales en el contrato común: un motor que no los guarda devuelve `null`.
- La clínica agenda citas y lleva odontograma.
- Rol `secretaria`: solo en esta clínica. Registra pacientes y gestiona citas, sin acceso
  clínico y sin poder archivar.
- Estado de cada pieza del odontograma: **lista fija** de 12 valores (`EstadoDental`),
  porque el frontend dibuja un odontograma interactivo con un color por estado.

## Colecciones

```text
pacientes/{idAuto}
  nombres, apellidos, fecha_nacimiento ("AAAA-MM-DD")
  contacto { telefono, correo, direccion }            ← embebido
  alergias_evaluadas: bool
  alergias [ { sustancia, reaccion, severidad } ]     ← embebido
  estado "Activo" | "Archivado"
  fecha_baja, motivo_baja, detalle_baja, archivado_por (al archivar)
  creado_en, actualizado_en

pacientes/{id}/consultas/{idAuto}                     ← subcolección
  id_profesional_central, fecha_hora, motivo, notas
  diagnosticos  [ { descripcion, codigo, sistema_codigo } ]   ← embebidos
  tratamientos  [ { descripcion } ]                           ← embebidos
  recetas       [ { medicamento, dosis, frecuencia, via_administracion,
                    duracion_dias, instrucciones } ]          ← embebidas

pacientes/{id}/odontograma/actual                     ← documento aparte
  piezas { "36": { estado, superficies[], nota, actualizado_por, actualizado_en } }
  estado ∈ sana | caries | obturada | corona | endodoncia | sellante | fractura |
          protesis | implante | extraccion_indicada | ausente | en_erupcion

profesionales/{uuidCentral}                           ← perfil local
  nombres, apellidos, rol, activo, sincronizado_en

citas/{idAuto}                                        ← colección raíz
  id_paciente, nombre_paciente (copia), id_profesional, inicio, fin,
  duracion_minutos, motivo, estado, creada_por, motivo_cambio, actualizada_por

agendas/{uuidProfesional}_{AAAA-MM-DD}                ← "candado" por día
  id_profesional, ocupado { idCita: { inicio, fin } }
```

## Por qué embeber o referenciar (lo que pide justificar el PDF)

| Dato | Decisión | Razón |
| --- | --- | --- |
| Contacto | Embebido en paciente | 1 a 1, pequeño, siempre se lee con el paciente. |
| Alergias | Embebidas en paciente | Lista corta y acotada (máx. 50). Se necesita en cada atención. `alergias_evaluadas` distingue "sin alergias" de "no preguntado". |
| Consultas | Subcolección del paciente | Crecen sin límite durante años. Un documento admite máx. 1 MiB. El historial se pagina con `order_by(fecha_hora).limit(n)` sin índice compuesto. |
| Diagnósticos, tratamientos, recetas | Embebidos en la consulta | Se registran juntos y son pocos. Un documento = una escritura atómica: no queda un diagnóstico a medias. Mismos campos que MongoDB. |
| Odontograma | Documento aparte, mapa de piezas | Acotado (máx. 52 piezas FDI). Separado del paciente porque es información clínica: la secretaria lee el paciente sin descargar el odontograma. |
| Profesional | Colección propia, ID = UUID central | Lo comparten muchas consultas y citas: se referencia. Sin correo ni contraseña; la identidad vive en PostgreSQL. |
| Citas | Colección raíz que referencia paciente y profesional | Se consultan por fecha (agenda del día), no por paciente. Copia de `nombre_paciente` para mostrar la agenda sin leer cada paciente. Si el nombre cambia, la cita conserva el nombre con que se agendó. |
| Agendas | Un documento por profesional y día | Firestore no tiene restricciones de unicidad ni de rangos. Este documento sirve de candado (ver abajo). |

## Consistencia y transacciones

Firestore no tiene llaves foráneas ni `UNIQUE`. La integridad se garantiza así:

| Operación | Mecanismo |
| --- | --- |
| Registrar paciente / actualizar pieza | `WriteBatch` en la unidad de trabajo, confirmado en `commit()`. |
| Registrar consulta | Transacción: vuelve a leer el paciente; si está archivado, no escribe. |
| Archivar | Transacción: solo si `estado == "Activo"`. Dos bajas simultáneas → una falla con 409. |
| Agendar cita | Transacción: lee los documentos `agendas/{prof}_{día}`, comprueba cruces y crea la cita y el horario ocupado juntos. Si dos secretarias reservan a la vez, Firestore detecta que el documento cambió y repite la transacción de una: la segunda recibe 409. |
| Cancelar cita | Transacción: cambia estado y libera el horario (`DELETE_FIELD`). |
| Estados de cita | `programada → atendida \| cancelada \| no_asistio`. Los estados finales no cambian. Cancelar exige motivo; "atendida" solo después de la hora. |

El día de la agenda se calcula en la zona `America/Guatemala` (`HISTORIALES_ZONA_HORARIA`).
Si una cita cruza la medianoche, se bloquean los dos días.

## Índices

Todas las consultas usan índices automáticos de un solo campo:

- Historial: rango y orden en `fecha_hora` de la subcolección.
- Agenda: rango y orden en `inicio`. El filtro por profesional se aplica en el servidor.
- Citas del paciente: igualdad en `id_paciente`. El orden se aplica en el servidor (son pocas).

Así no hace falta crear índices compuestos en la consola. Si la clínica creciera,
se crearía un índice `(id_profesional, inicio)` y el filtro se haría en Firestore.

## Seguridad y roles

- El SDK Admin entra por IAM y **no pasa por las Security Rules**: la API valida
  JWT y permisos de PostgreSQL antes de abrir el adaptador. Reglas en la consola:
  `allow read, write: if false;`.
- La clave está en `.secrets/firebase-adminsdk.json`, ignorada por Git y por Docker.

| Rol | Permisos | Ve |
| --- | --- | --- |
| secretaria | `pacientes:leer`, `pacientes:registrar`, `citas:leer`, `citas:gestionar` | Datos y contacto del paciente, agenda. Al registrar puede anotar alergias (opcional), pero **no** las ve después. **No** ve consultas, diagnósticos, recetas ni odontograma. **No** archiva. |
| odontologo | los anteriores que se le asignen + `historiales:leer`, `consultas:registrar` | Todo el historial clínico; registra consultas y odontograma. |

PostgreSQL impide con triggers que una secretaria reciba `historiales:leer`,
`consultas:registrar` o `historiales:archivar` (`006_rol_secretaria_citas.sql` y
`007_secretaria_restricciones.sql`), y con un `CHECK` que exista fuera de
`clinica_odontologica`.

Clasificación de la información:

- **Público:** catálogo de superficies dentales.
- **Confidencial:** nombre, contacto y agenda.
- **Restringido:** alergias, consultas, diagnósticos, recetas y odontograma.

## Perfiles de profesionales

`python -m scripts.crear_profesional ... --institucion clinica_odontologica` crea
también el perfil en `profesionales/`. No es una transacción entre motores: si
Firestore falla, la cuenta queda en PostgreSQL y se repite con
`python -m scripts.sincronizar_profesionales`, que es idempotente.

Referencias: [modelo de datos](https://firebase.google.com/docs/firestore/data-model),
[transacciones y batches](https://firebase.google.com/docs/firestore/manage-data/transactions),
[índices](https://firebase.google.com/docs/firestore/query-data/indexing),
[IAM y SDKs de servidor](https://firebase.google.com/docs/firestore/security/iam).
Numeración de piezas: FDI / ISO 3950.
