# Revisión del centro pediátrico

Se conserva el enfoque del dueño: pacientes y responsables, crecimiento, consultas,
especialidades, recetas y vacunas. El SQL original está en
`database/mysql/original/DB Hospital MySql.sql`; no se usa al arrancar Docker.
La inicialización revisada está en `database/mysql/001_hospital_pediatrico.sql`
y las reglas entre tablas en `002_integridad.sql`. Requieren MySQL 8.4 e InnoDB.
Como el proyecto todavía no tenía datos, se aplicó un modelo nuevo sin migrar filas.

## Cambios y motivo

| Antes | Modelo revisado y razón |
| --- | --- |
| Una alergia por paciente | `paciente_alergia` N:M, con reacción y observaciones. `alergias_evaluadas` distingue no evaluado de evaluado sin alergias registradas. |
| Un tutor obligatorio y parentesco en el tutor | `paciente_tutor` N:M; parentesco por relación. Un adulto puede ser madre de un paciente y tía de otro. Índice único generado permite como máximo un responsable principal autorizado. |
| Correo único por tutor | Correo opcional y compartible. El documento de identidad sigue siendo único cuando se conoce; no se inventa un DPI para poder registrar. |
| Estado sin archivo documentado | `archivado`, fecha y motivo de baja consistentes por CHECK. El estado operativo queda como catálogo extensible. Archivar conserva consultas y recetas. |
| Medidas y percentiles sin límites | Valores positivos y percentiles entre 0 y 100; medidas pueden faltar. Se conserva la referencia usada para los percentiles. No se impone una edad máxima pediátrica arbitraria. |
| Control de crecimiento de cualquier paciente | FK compuesta `(id_control, id_paciente)` garantiza que el control pertenece al paciente de la consulta, incluso después de editarlo. |
| Diagnóstico único de texto y sin tratamiento | Impresión general opcional más tablas de diagnósticos y tratamientos por consulta. Códigos clínicos opcionales y sistema de codificación explícito. |
| Receta con duración siempre obligatoria | Medicamento, dosis y frecuencia siguen siendo necesarios; duración y vía se amplían para indicaciones variables. Duración conocida debe ser positiva. |
| Lote obligatorio al programar una vacuna | Tipo de vacuna separado del lote. La programación puede existir antes de tener inventario asignado; al aplicar se exigen lote, fecha y médico aplicador. |
| Lote globalmente único, sin vencimiento | Lote único por tipo de vacuna; vencimiento requerido. FK compuesta asegura lote del tipo correcto. Aplicación descuenta stock mediante UPDATE condicional atómico. |
| Cobros del diagrama ausentes en SQL | Factura con líneas de cargo y pagos parciales. Importes exactos DECIMAL y monto de línea generado, sin datos de tarjeta. |
| Identidad aislada | `medico.id_profesional_central` enlaza lógicamente con el UUID central de PostgreSQL. Sin duplicar correo de acceso ni contraseña en MySQL. |

`consulta_medica` rechaza nuevas consultas para un paciente archivado o un médico
inactivo y consultas anteriores al nacimiento. El nacimiento no puede ser futuro.
La identidad de una consulta registrada no puede reasignarse a otro
paciente/médico; una corrección de identidad necesita un proceso trazable posterior.
Una vacunación aplicada conserva lote, paciente, fecha y aplicador. Puede ampliarse
su observación, pero no borrarse ni transformarse de nuevo en pendiente para alterar stock.

## Optimización y concurrencia

Los índices compuestos de consulta y crecimiento comienzan por paciente y fecha,
con el ID como desempate para futuras páginas de historial. No se crean índices
en todas las columnas. Los índices únicos y FKs también evitan búsquedas ambiguas.

Los acumulados de factura son una desnormalización deliberada: los triggers de
INSERT/UPDATE/DELETE de líneas y pagos los mantienen en la misma transacción.
El CHECK de cabecera obliga a que lo pagado no supere lo facturado. Bloquear la
cabecera antes del INSERT evita la conversión concurrente de bloqueos compartidos
de las FKs. Dos pagos de 80 contra una factura de 100 permiten uno y rechazan el otro.
Reducir/eliminar cargos bajo lo ya pagado también se rechaza. La vista de saldos usa
estos acumulados sin agrupar todas las líneas en cada lectura.

El backend actualmente solo tiene SELECT sobre paciente. Al habilitar facturación,
dar permisos por columnas: nunca permitir que la aplicación escriba directamente
`total_facturado` ni `total_pagado`. El administrador de BD puede alterar datos y
reglas; esa capacidad no se entrega al usuario de la aplicación.

## Límites que debe cubrir el adaptador de escritura

- Registrar consulta, diagnósticos, tratamientos y recetas en una transacción, con
  rollback completo y reintento acotado ante deadlocks. No reintentar errores de validación.
- Validar que el UUID central del médico pertenece al centro pediátrico. Una FK
  de MySQL no puede apuntar a PostgreSQL; esta comprobación corresponde al backend.
- Acordar si se exige tutor antes de finalizar un registro infantil. Se permite
  crear el expediente mientras se identifican responsables; la BD limita duplicados.
- Documentar si cantidad significa dosis disponibles. Hoy cada aplicación consume
  una unidad; frascos multidosis requerirían unidades y movimientos de inventario.
- Registrar auditoría y rectificaciones; no dar DELETE de historiales a usuarios.
  Los errores médicos no deben corregirse borrando su evidencia.
- Completar consistencia de fechas en controles de crecimiento, modificaciones de
  consultas y rectificaciones del nacimiento al definir el contrato de escritura.
  No se inventan rangos médicos o protocolos de vacunación.

Facturación es un módulo sencillo de cargos/pagos, no facturación fiscal. El diagrama
también menciona personal operativo; por ahora se conserva `medico`, como en el SQL
del dueño. Si enfermería aplicará vacunas, generalizar esa tabla y su FK antes de
habilitar dicha operación; el login central ya contempla ese rol.

## Clasificación

Catálogos de vacunas, alergias y especialidades: públicos en contenido, su publicación
se decide mediante endpoints. Nombres, contacto, tutores, documentos y UUID de
profesionales: confidenciales. Diagnósticos, recetas, alergias de un paciente,
resultados y notas: restringidos. Religión y salario son opcionales y restringidos;
no se incluyen en la respuesta común de paciente. La clasificación requiere permisos
efectivos en la API y cuentas de BD limitadas; un comentario SQL por sí solo no protege datos.

Referencias: [CHECK de MySQL](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html),
[triggers](https://dev.mysql.com/doc/refman/8.4/en/triggers.html).
