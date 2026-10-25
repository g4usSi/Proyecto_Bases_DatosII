# Operaciones comunes: esqueleto para trabajar en equipo

La API completa del curso ya existe y **los cuatro motores implementan las cinco
operaciones** (registrar, leer, historial, consulta con diagnósticos/tratamientos/recetas
y archivar) más la búsqueda por nombre. Lo que un motor no ofrece responde **501** con el
motor y la operación, por ejemplo `MySQL: 'citas' todavia no esta implementado.` Hoy eso
solo ocurre con los módulos propios de un establecimiento (odontograma, pediatría y
laboratorio) fuera de su motor. Referencia completa: [documentacion-backend.md](../documentacion-backend.md).

## Rutas y permisos

| Ruta | Caso de uso | Permiso |
| --- | --- | --- |
| `POST /api/v1/pacientes` | `RegistrarPaciente` | `pacientes:registrar` |
| `GET /api/v1/pacientes?nombre=&limite=` | `BuscarPacientes` | `pacientes:leer` |
| `GET /api/v1/pacientes/{id}` | `ConsultarPaciente` | `pacientes:leer` |
| `GET /api/v1/pacientes/{id}/historial?limite=20&antes_de=` | `ConsultarHistorial` | `historiales:leer` |
| `POST /api/v1/pacientes/{id}/consultas` | `RegistrarConsulta` | `consultas:registrar` |
| `PATCH /api/v1/pacientes/{id}` | `ActualizarPaciente` | `pacientes:registrar` |
| `POST /api/v1/pacientes/{id}/alergias` | `AgregarAlergias` | `pacientes:registrar` |
| `GET /api/v1/pacientes/{id}/consultas/{id_consulta}` | `ConsultarConsulta` | `historiales:leer` |
| `POST /api/v1/pacientes/{id}/consultas/{id_consulta}/adenda` | `AgregarAConsulta` | `consultas:registrar` |
| `POST /api/v1/pacientes/{id}/archivo` | `ArchivarPaciente` | `historiales:archivar` |
| `GET /api/v1/pacientes/{id}/citas` | `CitasDePaciente` | `citas:leer` |
| `POST /api/v1/citas` | `AgendarCita` | `citas:gestionar` |
| `GET /api/v1/citas?desde=&hasta=&id_profesional=` | `ConsultarAgenda` | `citas:leer` |
| `POST /api/v1/citas/{id}/estado` | `CambiarEstadoCita` | `citas:gestionar` |
| `GET /api/v1/pacientes/{id}/odontograma` | `ConsultarOdontograma` | `historiales:leer` |
| `PUT /api/v1/pacientes/{id}/odontograma/piezas/{pieza}` | `ActualizarPieza` | `consultas:registrar` |

Pediatría (solo MySQL): `/pacientes/{id}/crecimiento`, `/vacunas` (solo tipos; sin lotes ni stock),
`/pacientes/{id}/vacunacion` (+ `esquema-recomendado`, `{id_dosis}/aplicar|cancelar`).
Laboratorio (solo MongoDB): `/laboratorio/pruebas`, `/pacientes/{id}/ordenes` (+ `muestras`,
`pruebas/{codigo}/resultados`, `validar`, `cancelar`), con los permisos nuevos
`laboratorio:resultados` y `laboratorio:validar` (rol `laboratorista`). Detalle por ruta en
[documentacion-backend.md](../documentacion-backend.md).

Las alergias del paciente solo se muestran a quien tiene `historiales:leer`.
Los permisos de citas y el rol `secretaria` llegan con `006_rol_secretaria_citas.sql`;
las restricciones de la secretaria (solo clínica odontológica, sin archivar) con
`007_secretaria_restricciones.sql`.

Estado de una pieza del odontograma: lista fija (`sana`, `caries`, `obturada`, `corona`,
`endodoncia`, `sellante`, `fractura`, `protesis`, `implante`, `extraccion_indicada`,
`ausente`, `en_erupcion`). Otro valor responde 422.
Para probar un odontólogo con todos los permisos:

```powershell
python -m scripts.crear_profesional --correo odonto@example.com --nombres "Ana" --apellidos "Prueba" --institucion clinica_odontologica --rol odontologo --permiso pacientes:leer --permiso pacientes:registrar --permiso historiales:leer --permiso consultas:registrar --permiso historiales:archivar --permiso citas:leer --permiso citas:gestionar
```

Y una secretaria (solo `clinica_odontologica`; recibe sus permisos por defecto y no admite
`historiales:archivar`):

```powershell
python -m scripts.crear_profesional --correo recepcion@example.com --nombres "Eva" --apellidos "Prueba" --institucion clinica_odontologica --rol secretaria
```

Códigos: 401 sesión, 403 permiso, 404 paciente/cita ausente, 409 historial archivado
u horario ocupado, 422 datos inválidos, 501 pendiente en ese motor, 503 motor no disponible.

## Dónde está cada pieza

```text
app/domain/paciente.py, consulta.py      Entidades comunes (no dependen del motor)
app/application/ports/                   Contratos que cada motor implementa
app/application/use_cases/               Reglas comunes: existe, no archivado, commit
app/presentation/api/routes/pacientes.py HTTP; igual para los cuatro motores
app/infrastructure/persistence/          Adaptadores por motor  ← aquí trabaja cada rama
app/infrastructure/persistence/pendiente.py  Piezas provisionales (501)
```

Las reglas que no dependen del motor van en el caso de uso, no en el adaptador. Por
ejemplo: "no registrar consultas en un historial archivado" ya está en `RegistrarConsulta`.
Al adaptador le toca guardar y leer, de forma atómica.

## Estado por motor

| Motor | registrar | leer | buscar | historial | consulta | archivar | citas | odontograma |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PostgreSQL (`postgresql/unidad.py`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | no aplica |
| MySQL (`mysql/unidad.py`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (+ crecimiento y vacunas) | no aplica |
| MongoDB (`mongodb/unidad.py`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (+ laboratorio) | no aplica |
| Firestore (`firestore/unidad.py`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### Búsqueda por nombre (regla común)

Está en `app/domain/busqueda.py` y la cumplen los cuatro motores: cada palabra buscada debe
ser el **comienzo** de alguna palabra de "nombres apellidos", sin importar mayúsculas ni
acentos (`jose mar` encuentra a "María José Pérez"). Mínimo 2 letras, hasta 5 palabras.
Incluye historiales archivados (el resultado indica `archivado`) y ordena por apellidos,
nombres e identificador. Devuelve un resumen sin contacto ni alergias.

| Motor | Cómo se logra |
| --- | --- |
| PostgreSQL | `unaccent()` + `lower()` + `LIKE` (extensión creada en `008`). |
| MySQL | Colación `utf8mb4_0900_ai_ci` (ignora acentos y mayúsculas) + `LIKE`. |
| MongoDB | `$regex` con clases de letras (`[eEéÉ…]`), porque MongoDB no ignora acentos en regex. |
| Firestore | Campo `prefijos_nombre` + `array_contains` y filtro en memoria. |

En todos los motores los comodines que escriba el usuario (`%`, `_`, `.`, `*`…) se tratan
como texto.

### Cómo resuelve cada motor la consistencia

| Motor | Consulta + diagnósticos + tratamientos + recetas | Consulta vs. baja simultáneas | Dos bajas simultáneas |
| --- | --- | --- | --- |
| PostgreSQL | Una transacción; filas en `atencion`, `diagnostico`, `tratamiento`, `orden_medica`, `receta` y `detalle_receta`. | `SELECT … FOR SHARE` sobre el paciente + trigger `trg_atencion_paciente_activo`. | `UPDATE … WHERE estado = 'Activo'`. |
| MySQL | Una transacción InnoDB. | `SELECT … FOR UPDATE` sobre el paciente + trigger de `002_integridad.sql`. | `UPDATE … WHERE archivado = FALSE`. |
| MongoDB | Un solo documento (atómico por sí mismo), con todo embebido. | Escritura condicional previa sobre el paciente (ver abajo). | `update_one` con `estado: 'Activo'`. |
| Firestore | Transacción/batch. | Transacción. | Transacción. |

Notas por motor que conviene recordar:

- **PostgreSQL:** en el modelo del hospital un tratamiento cuelga de un *diagnóstico*; el
  contrato común no dice de cuál, así que se guarda bajo el primero. Un tratamiento sin
  ningún diagnóstico responde 422. La cuenta de la API no puede borrar datos clínicos.
- **MySQL:** la fecha de nacimiento es obligatoria (422 si falta). El `numero_expediente`
  se genera (`CP-…`). Las alergias usan el catálogo compartido `alergias_conocidas`
  (misma sustancia con otra capitalización o acento = la misma fila). El código de
  colegiado real lo completa el hospital; la sincronización pone `PEND-<uuid>`.
- **MongoDB:** es un servidor único, sin transacciones. Las escrituras se acumulan y se
  ejecutan en `commit()`. Antes de insertar la consulta se hace una escritura condicional
  sobre el paciente (`estado: Activo`) que sirve de punto de serialización con la baja;
  una consulta aceptada milisegundos antes de la baja puede terminar de guardarse justo
  después. Quedó documentado como límite conocido: con un *replica set* se usaría una
  transacción y la ventana desaparece. Los textos vacíos se omiten porque el validador del
  laboratorio exige texto visible; las fechas tienen precisión de milisegundo.

### Cuentas y profesionales locales

Para registrar una consulta, la cuenta central debe estar vinculada al profesional local
(`personal_medico`, `medico` o la colección `profesionales`). Si no, la API responde 403
con el mensaje para ejecutar la sincronización:

```powershell
python -m scripts.sincronizar_profesionales
```

`scripts.crear_profesional` ya lo hace automáticamente al crear la cuenta (si el motor
local no está disponible, avisa y se puede repetir la sincronización). Es idempotente y
no pisa el colegiado ni un estado "Suspendido" puesto por el hospital. MySQL y MongoDB
usan sus cuentas administrativas (`MYSQL_ROOT_PASSWORD`, `MONGO_ROOT_PASSWORD` del `.env`).

### Si tu volumen de Docker ya existía

Docker solo ejecuta `database/` con un volumen vacío. Las migraciones nuevas se aplican a
mano, una sola vez (son idempotentes, repetirlas no daña nada):

```powershell
Get-Content database\postgresql\008_escritura_api.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
Get-Content database\mysql\004_escritura_api.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
Get-Content database\mysql\005_permisos_escritura.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
```

MongoDB no necesita migración: el validador ya acepta los campos que escribe la API.
Después: `python -m scripts.sincronizar_profesionales`.

### Para completar citas y odontograma en otro motor

Firestore sirve de implementación de referencia. El Hospital General también maneja citas
en su SQL original; puede implementar `RepositorioCitas` con una restricción de exclusión o
una transacción `SERIALIZABLE`.

1. Busca su `pendiente("<motor>", ...)` y reemplázalo por la implementación real.
2. Crea un repositorio que implemente `RepositorioCitas` y asígnalo en tu unidad de
   trabajo en lugar del pendiente.
3. **Permisos de base de datos:** la cuenta de la API solo recibe los `GRANT` mínimos. Agrega
   los nuevos en una migración numerada (como `008` y `005`), sin `DELETE`.
4. Agrega pruebas de integración en `tests/integration/test_<motor>_api.py`.
5. Corre `python -m pytest`, `python -m ruff check .` y `python -m ruff format --check .`.

## Pendiente de acordar entre todos

- Acordado: cada motor guarda solo los datos que su institución necesita; `contacto`
  y `alergias` son opcionales en el contrato común.
- Si una consulta exige al menos un diagnóstico.
- Regla de duplicados al registrar paciente.
- Auditoría y rectificación antes de permitir corregir consultas ya guardadas.
