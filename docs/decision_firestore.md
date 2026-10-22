# Decisión: Firebase/Cloud Firestore

Actualizado el 21 de octubre de 2026.

## Decisión del equipo

Para la Clínica Odontológica, FastAPI se conectará directamente a Cloud Firestore
desde el servidor usando el SDK Admin oficial para Python. No se montará Firebase
Emulator Suite como requisito de la entrega. En el habla cotidiana se puede decir
“conectar por API”, pero aquí no hace falta construir llamadas REST manuales: el
SDK Admin es el cliente de servidor que se comunica con Firestore.

Esto reduce piezas locales si ya existe un proyecto Firebase accesible. No elimina
la configuración cloud: hay que habilitar Firestore, escoger una ubicación,
configurar identidad del servidor y revisar facturación/cuotas. Como todavía no se
confirmó que el equipo tenga acceso a un proyecto, si crear permisos/proyecto toma
más tiempo que instalar el emulador, cambiar a Emulator Suite sigue siendo una
alternativa razonable para desarrollo y pruebas.

## Acceso y seguridad

- FastAPI conserva PostgreSQL como autoridad de identidad. No se agrega Firebase
  Auth ni se deja que el cliente elija la institución.
- La API valida el JWT y los permisos del profesional en PostgreSQL antes de abrir
  el adaptador de Firestore, igual que con los otros motores.
- El SDK Admin de servidor se autoriza mediante Google Cloud IAM y omite las
  Firestore Security Rules. Por eso esas reglas no son el control de autorización
  de las solicitudes del backend: deben protegerse la cuenta de servicio/IAM y la
  autorización de la API. No conceder roles amplios de Editor/Owner; elegir el
  acceso de datos mínimo necesario para el proyecto.
- En una máquina local, usar Application Default Credentials si el flujo del equipo
  lo permite. Si se requiere una clave de cuenta de servicio, guardarla fuera del
  repositorio y de la imagen Docker, limitar sus permisos y no compartirla por chat.
  En Docker, montar el archivo de credenciales como solo lectura y pasar únicamente
  la ruta mediante configuración del proceso; no copiar la clave al contenedor.
- Trabajar con expedientes sintéticos para la presentación. No cargar información
  real de pacientes en el proyecto académico.

## Cuotas y costo

La documentación oficial publica una cuota gratuita para Firestore Standard que
incluye 1 GiB almacenado, 50.000 lecturas diarias, 20.000 escrituras diarias,
20.000 eliminaciones diarias y 10 GiB mensuales de transferencia saliente. El
proyecto dispone de una sola base de datos sin costo. Con facturación habilitada,
el uso que exceda cuotas puede generar cargos; sin facturación, las operaciones
pueden dejar de estar disponibles al llegar a los límites gratuitos. Funciones como
copias de seguridad, recuperación a un punto en el tiempo y algunas eliminaciones
TTL requieren facturación. Antes de usar el proyecto, revisar la pantalla de
uso/facturación y mantener el prototipo dentro de sus límites.
Estas cifras son referencia de la documentación consultada el 21 de octubre de
2026 y pueden cambiar.

## Pasos de implementación pendientes

1. Confirmar el proyecto Firebase de equipo, crear la base de datos Firestore en una
   ubicación elegida por el equipo y verificar si el plan/cuotas cubren la demo.
2. Agregar `firebase-admin` a las dependencias de Python y documentar la variable
   de entorno que indica credenciales; no guardar valores secretos en `.env.example`.
3. Inicializar el cliente una sola vez en el ciclo de vida de FastAPI y cerrarlo o
   liberarlo al apagar la aplicación si el cliente lo requiere.
4. Implementar la fábrica de la Clínica Odontológica y el repositorio de pacientes
   con el mismo contrato HTTP que usan los otros motores. No inventar aún el esquema
   de odontología: definir sus colecciones/campos e índices a partir del enunciado
   y de la información del dueño del modelo.
5. Validar la estructura documental en la aplicación y definir claves de paciente,
   referencias, borrado/archivo, duplicados e índices. Firestore no ofrece llaves
   foráneas relacionales; la integridad entre documentos debe resolverse mediante
   validaciones y transacciones/batches cuando aplique.
6. Probar con un proyecto de pruebas y documentos sintéticos. Si se requiere
   aislamiento sin costo o las credenciales cloud no están disponibles, valorar el
   emulador para las pruebas; no cambiar producción/demo silenciosamente.

## Fuentes oficiales

- [Firestore: inicio rápido para servidores con Python](https://firebase.google.com/docs/firestore/quickstart-server)
- [Firestore: IAM y SDKs de servidor](https://firebase.google.com/docs/firestore/security/iam)
- [Firestore: precios y cuota gratuita](https://firebase.google.com/docs/firestore/pricing)
- [Google Cloud: configurar Application Default Credentials localmente](https://cloud.google.com/docs/authentication/set-up-adc-local-dev-environment)
- [Google Cloud: buenas prácticas para claves de cuentas de servicio](https://cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys)
