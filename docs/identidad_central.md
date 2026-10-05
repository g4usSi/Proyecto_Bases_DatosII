# Identidad central

Decisión del equipo: exclusivamente profesionales de la salud y un establecimiento
por profesional. PostgreSQL contiene el esquema `identidad`, separado del esquema
clínico `public` del Hospital General. MySQL, MongoDB y posteriormente Firestore
guardan sus propios datos clínicos. La API es el punto de acceso común.

1. Una herramienta administrativa crea el profesional con UUID, correo normalizado,
   hash Argon2id, rol, establecimiento y permisos explícitos.
2. `POST /api/v1/auth/login` recibe solamente correo y contraseña en JSON. El
   cliente no puede elegir establecimiento ni motor.
3. PostgreSQL entrega la institución vinculada y la API emite un JWT HS256 firmado
   con vigencia de 30 minutos por defecto, emisor y audiencia definidos.
4. En cada solicitud se valida firma/vencimiento y se vuelve a consultar el estado,
   establecimiento, permisos y versión de sesión en PostgreSQL. No confiar en
   permisos almacenados en el token.
5. La fábrica resuelve el repositorio clínico por esa institución verificada.

El JWT contiene identificador, institución, versión y metadatos de sesión; no
incluye información clínica, correo ni hash. La clave permanece en `.env`, ignorado
por Git. El generador produce secretos aleatorios y conserva valores existentes.
La API usa una cuenta PostgreSQL limitada, no la cuenta administrativa de altas.

`POST /auth/logout` incrementa la versión e invalida **todas** las sesiones de ese
profesional. Desactivar cuenta o establecimiento también impide uso de tokens ya
emitidos. Reasignar establecimiento invalida el token anterior. Cambiar contraseña
administrativamente debe incrementar `version_token` en la misma transacción.

Después de cinco contraseñas fallidas se bloquean nuevos logins por 15 minutos,
con contador persistido en PostgreSQL. Los errores no revelan si un correo existe.
La contraseña se verifica con un hash ficticio cuando la cuenta no existe. Las
respuestas de validación no reflejan entradas que puedan contener contraseñas.

## Crear la primera cuenta

Con las bases ejecutándose, desde PowerShell en la raíz:

```powershell
python -m scripts.crear_profesional --correo medico@example.com --nombres "Nombre" --apellidos "Apellido" --institucion centro_pediatrico --rol medico
```

La contraseña se pide oculta, dos veces. Se otorga solamente `pacientes:leer` por
defecto; usar `--permiso` repetido para permisos adicionales existentes. El alta es
atómica: un correo repetido o permiso desconocido revierte toda la operación.
Crear cuenta no crea ni modifica un médico local automáticamente. El UUID impreso
se vincula al profesional local antes de habilitar escrituras de consultas.

En Swagger, ejecutar login, copiar `access_token` y pegarlo en **Authorize**. Después
probar `/auth/me` y la consulta de paciente. Una base vacía devuelve 404 para un ID
ausente; no significa que la conexión haya fallado.

Antes de publicar fuera del equipo: HTTPS y límite de peticiones por origen para
reducir intentos masivos a correos inexistentes; auditoría de accesos y un flujo de
recuperación/rectificación de cuentas. Esta entrega prepara el login local, no ese
despliegue. Firebase queda pendiente como almacenamiento clínico de odontología;
no se necesita Firebase Auth para la identidad central elegida.

La identidad transversal debe explicarse en la documentación de evaluación:
PostgreSQL administra acceso, pero no copia ni reemplaza los historiales de los
otros tres motores. Las cuatro operaciones clínicas comunes siguen pendientes de
completar en todos los adaptadores.

Referencia: [FastAPI, hashing y JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
