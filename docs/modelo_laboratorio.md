# Laboratorio clínico en MongoDB

El script `laboratorio_clinico_mongo.js` está en la raíz y se ejecuta con mongosh.
Compose lo ejecuta automáticamente al inicializar un volumen vacío. Se puede
repetir: actualiza validadores y asegura índices sin borrar documentos. Si ya
existieran duplicados, un índice único podría fallar; actualizar el validador no
revisa retroactivamente todos los documentos existentes.

| Colección | Diseño |
| --- | --- |
| `pacientes` | Datos básicos y contacto; alergias como conjunto acotado clínico. Archivo exige fecha/motivo. Expediente único. |
| `profesionales` | Perfil local enlazado con UUID de PostgreSQL, sin credenciales. |
| `catalogo_pruebas` | Código y versión únicos; parámetros, tipos y referencia de medición. No contiene rangos clínicos inventados. |
| `consultas` | Un documento por atención con diagnósticos, tratamientos y recetas embebidos. Contrato común de los cuatro establecimientos. |
| `ordenes_laboratorio` | Una orden por documento, referencias al paciente/consulta, muestras y pruebas/resultados embebidos. Conserva versión y rangos usados en ese examen. |

La consulta embebe los datos que se registran juntos para poder insertarlos
atómicamente. No se embebe el historial completo en paciente: crecería sin límite.
Las consultas y órdenes usan índices paciente-fecha-ID para paginación estable.
Una orden validada necesita autor, fecha y resultados de todas sus pruebas; los
valores numéricos, de texto y booleanos se validan según `tipo_valor`.

Se conservan unidades y referencia aplicada como copia histórica. El catálogo se
versiona; actualizar rangos futuros no cambia el significado de resultados pasados.
No automatizar diagnóstico ni interpretación médica solo por un rango numérico.

## Integridad y transacciones

MongoDB valida tipos y forma, pero estas referencias no son llaves foráneas. El
adaptador de escritura debe comprobar paciente/consulta existentes, que la consulta
corresponde al paciente y que el UUID profesional pertenece al laboratorio. Además,
debe coordinar la comprobación de paciente activo con un archivo concurrente.

El contenedor actual es standalone y el adaptador implementado es solo de lectura.
Una escritura de un documento es atómica. Operaciones que cambien paciente, consulta
y orden simultáneamente requerirán un replica set y transacciones, con reintentos,
antes de habilitar esos endpoints. No se promete una transacción entre PostgreSQL
y MongoDB: PostgreSQL autoriza y el motor clínico conserva el expediente.

La cuenta local `historiales_app` solo accede a esta base; se crea leyendo un secreto
del entorno del contenedor. Las credenciales y los tokens no van en las colecciones.
Los puertos de Docker están publicados exclusivamente en 127.0.0.1.

Catálogo de pruebas: público en contenido. Identidad, contacto y perfiles:
confidenciales. Resultados, órdenes, diagnósticos, recetas y alergias: restringidos.
Aplicar permisos en el backend; el validador no sustituye la autorización.

Referencias: [validación de esquema](https://www.mongodb.com/docs/manual/core/schema-validation/),
[modificación de validadores](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/),
[transacciones](https://www.mongodb.com/docs/manual/core/transactions/).
