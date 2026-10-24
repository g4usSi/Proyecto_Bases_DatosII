# Operaciones comunes: esqueleto para trabajar en equipo

La API completa del curso ya existe. Cada motor va reemplazando sus piezas
pendientes, sin cambiar las rutas ni las respuestas. Mientras una pieza falte,
la API responde **501** con el motor y la operación que faltan, por ejemplo
`MySQL: 'registrar consulta' todavia no esta implementado.`

## Rutas y permisos

| Ruta | Caso de uso | Permiso |
| --- | --- | --- |
| `POST /api/v1/pacientes` | `RegistrarPaciente` | `pacientes:registrar` |
| `GET /api/v1/pacientes/{id}` | `ConsultarPaciente` | `pacientes:leer` |
| `GET /api/v1/pacientes/{id}/historial?limite=20&antes_de=` | `ConsultarHistorial` | `historiales:leer` |
| `POST /api/v1/pacientes/{id}/consultas` | `RegistrarConsulta` | `consultas:registrar` |
| `POST /api/v1/pacientes/{id}/archivo` | `ArchivarPaciente` | `historiales:archivar` |
| `GET /api/v1/pacientes/{id}/citas` | `CitasDePaciente` | `citas:leer` |
| `POST /api/v1/citas` | `AgendarCita` | `citas:gestionar` |
| `GET /api/v1/citas?desde=&hasta=&id_profesional=` | `ConsultarAgenda` | `citas:leer` |
| `POST /api/v1/citas/{id}/estado` | `CambiarEstadoCita` | `citas:gestionar` |
| `GET /api/v1/pacientes/{id}/odontograma` | `ConsultarOdontograma` | `historiales:leer` |
| `PUT /api/v1/pacientes/{id}/odontograma/piezas/{pieza}` | `ActualizarPieza` | `consultas:registrar` |

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

## Qué falta en cada motor

| Motor | registrar paciente | leer paciente | historial | registrar consulta | archivar | citas | odontograma |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PostgreSQL (`sql.py`) | 501 | ✅ | 501 | 501 | 501 | 501 | no aplica |
| MySQL (`sql.py`) | 501 | ✅ | 501 | 501 | 501 | 501 | no aplica |
| MongoDB (`mongodb/lectura.py`) | 501 | ✅ (+estado, contacto, alergias) | 501 | 501 | 501 | 501 | no aplica |
| Firestore (`firestore/unidad.py`) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Firestore sirve de **implementación de referencia**: copien su estructura
(qué valida el caso de uso y qué valida el adaptador) en su motor.
El Hospital General también maneja citas en su SQL original; puede implementar
`RepositorioCitas` con una restricción de exclusión o una transacción `SERIALIZABLE`.

Para implementar una operación en tu motor:

1. Busca su `pendiente("<motor>", ...)` y reemplázalo por la implementación real.
2. Para historial o citas, crea un repositorio que implemente `RepositorioHistorial`
   o `RepositorioCitas` y asígnalo en tu unidad de trabajo en lugar del pendiente.
3. Mapea `archivado` al leer el paciente (hoy SQL siempre devuelve `False`).
4. **Permisos de base de datos:** las cuentas de la API solo pueden leer `paciente`
   en PostgreSQL y MySQL. Para escribir, agrega los `GRANT` mínimos en una migración nueva
   numerada (p. ej. `database/postgresql/007_permisos_escritura.sql`).
5. **Los volúmenes ya existen:** Docker solo ejecuta los scripts de `database/` con
   un volumen vacío. Una migración nueva se aplica a mano, por ejemplo:
   `Get-Content database\postgresql\007_x.sql | docker compose exec -T postgres psql -U historiales_admin -d hospital_general`.
6. Agrega pruebas de integración en `tests/integration/test_<motor>.py`.
7. Corre `python -m pytest`, `python -m ruff check .` y `python -m ruff format --check .`.

## Pendiente de acordar entre todos

- Acordado: cada motor guarda solo los datos que su institución necesita; `contacto`
  y `alergias` son opcionales en el contrato común.
- Si una consulta exige al menos un diagnóstico.
- Regla de duplicados al registrar paciente.
- Auditoría y rectificación antes de permitir corregir consultas ya guardadas.
