# Arquitectura de la base

## Recorrido de una solicitud

1. FastAPI recibe la solicitud y valida sus parámetros HTTP.
2. El autenticador verifica el token y devuelve usuario, institución y permisos.
3. Se comprueba el permiso requerido por la operación.
4. El contenedor crea una unidad de trabajo para la institución verificada.
5. El caso de uso utiliza los repositorios definidos por los puertos.
6. El adaptador consulta su motor y convierte el resultado en entidades del dominio.
7. La capa HTTP convierte el resultado en el mismo contrato de respuesta para todos.

La solicitud no elige el motor mediante cabeceras, parámetros o datos del formulario.
La configuración vincula una institución con una fábrica de adaptadores. Las
cuatro fábricas pueden coexistir en una misma aplicación.

## Responsabilidad de las capas

| Capa | Responsabilidad |
| --- | --- |
| `domain` | Entidades y reglas que no dependen del almacenamiento. |
| `application` | Casos de uso y puertos requeridos para ejecutar una operación. |
| `infrastructure` | Drivers, consultas SQL, documentos y autenticación concreta. |
| `presentation` | HTTP, validación de entrada, respuestas y autenticación de solicitudes. |
| `bootstrap` | Componer los adaptadores y crear dependencias por institución. |
| `core` | Leer configuración del proceso. |

`Paciente` es un contrato inicial de lectura, no un historial clínico completo.
Los identificadores se expresan como texto fuera del adaptador y se interpretan
en el contexto de una institución. Un adaptador SQL puede convertirlos a enteros;
un adaptador documental puede utilizar identificadores de documentos.

## Adaptadores iniciales

La fábrica `app/bootstrap/factory.py` registra lectura real para PostgreSQL,
MySQL y MongoDB cuando su configuración está presente. Firestore continúa pendiente;
la decisión es conectar su adaptador al servicio cloud desde el servidor, sin
requerir un emulador local. Ver [decisión de Firestore](decision_firestore.md).
Los motores implementan `RepositorioPacientes` y una unidad de trabajo por solicitud:

```python
# Resumen del registro; las fábricas concretas están en bootstrap/factory.py.
contenedor.unidades_trabajo[Institucion.HOSPITAL_GENERAL] = fabrica_postgresql
contenedor.unidades_trabajo[Institucion.CENTRO_PEDIATRICO] = fabrica_mysql
contenedor.unidades_trabajo[Institucion.LABORATORIO_CLINICO] = fabrica_mongodb
contenedor.unidades_trabajo[Institucion.CLINICA_ODONTOLOGICA] = fabrica_firestore
```

Las unidades SQL abren conexiones por solicitud y revierten/cerran al salir. MongoDB
comparte un MongoClient que administra su pool, cerrado con el ciclo de vida de
FastAPI. Su unidad es únicamente de lectura; commit explícitamente rechaza escrituras
todavía no implementadas. No compartir una transacción mutable entre usuarios.

## Consistencia

La unidad de trabajo define el límite de una operación. Sus adaptadores deben
liberar recursos al salir y revertir cambios no confirmados. Los futuros casos de
uso de escritura llamarán a `commit()` únicamente cuando termine la operación.

Para `registrar_consulta`, deberá acordarse qué diagnósticos, tratamientos y recetas
forman una sola operación atómica. Cada motor documentará cómo garantiza ese límite,
incluyendo los reintentos necesarios. Una transacción entre motores distintos no
forma parte de esta base: cada solicitud trabaja sobre los datos de una institución.

## Identidad central implementada

`AutenticadorCentral` valida JWT firmado, expiración, emisor y audiencia. El directorio
de PostgreSQL confirma usuario activo, institución, permisos y versión en cada
solicitud. La cuenta está ligada a una sola institución, según la decisión del equipo.
El formulario de login no acepta institución/motor. El backend usa credenciales de BD
limitadas; las cuentas administrativas solo se usan en herramientas locales.
Ver [diseño y alta de profesionales](identidad_central.md).

PostgreSQL centraliza identidad; la API conecta con el motor clínico autorizado.
El esquema clínico de PostgreSQL conserva el SQL recibido y requiere una revisión
adicional de pagos concurrentes/actualizaciones, ocupación de camas y consistencia
entre cita y atención antes de exponer esos módulos como escrituras. Esta etapa
únicamente lo utiliza para lectura de paciente y la identidad central nueva.

## Próximos contratos comunes

Antes de ampliar los adaptadores, definir juntos las entradas, salidas y reglas de:

- Registrar, buscar y actualizar pacientes.
- Registrar consultas con diagnósticos, tratamientos y recetas.
- Consultar el historial ordenado y paginado.
- Archivar el historial por baja del paciente.

Los campos específicos, como resultados de laboratorio o vacunas, extenderán el
modelo común de forma explícita. Las ramas de motores no deben inventar respuestas
HTTP incompatibles ni trasladar los casos de uso a la capa de drivers.
