# Avance de la Entrega II (estimado al 4 de noviembre de 2026)

Estimación del equipo contra los "Resultados esperados" del PDF. Los pesos son
propios, no de la rúbrica; actualizar esta tabla cuando cambie el estado.

## Resumen

| Parte | Avance |
| --- | --- |
| Backend (API + motores) | **≈ 99 %** |
| Frontend (cliente) | **≈ 98 %**: acceso, administración y pantallas clínicas de las cuatro instituciones |
| Documento comparativo | **≈ 30 %**: el material está repartido en `docs/`, sin redactar |
| Entrega II completa (backend 50 %, frontend 30 %, documento 20 %) | **≈ 85 %** |

## Backend

| Área (peso) | Avance | Detalle |
| --- | --- | --- |
| Base común (20 %) | 95 % | FastAPI hexagonal, login JWT, enrutamiento por usuario, permisos, roles, Docker. |
| Modelo por motor (20 %) | 85 % | Firestore 100 %. MySQL y MongoDB 90 %. PostgreSQL 70 % (reglas pendientes del SQL original: pagos, camas, cita/atención). |
| Operaciones comunes en 4 motores (40 %) | 100 % | 20 de 20 (5 operaciones × 4 motores) más búsqueda por nombre. Citas y odontograma solo en Firestore (extra de la clínica). |
| Consistencia demostrada (10 %) | 85 % | Pruebas de concurrencia (dos bajas, consulta vs. baja) en PostgreSQL, MySQL, MongoDB y Firestore. MongoDB: sin transacciones (servidor único); queda una ventana de milisegundos documentada. |
| Pruebas (10 %) | 95 % | Unitarias de todas las rutas. Integración real por motor (datos sintéticos, cuenta limitada de la API, flujo completo con login). Arranque desde cero en Docker comprobado el 4 de noviembre (volúmenes nuevos, migraciones, cuentas demo y flujo de hospital y laboratorio). |

Operaciones por motor (✅ hecho, — pendiente):

| | Registrar | Leer | Buscar | Historial | Consulta + diagnóstico + receta | Archivar |
| --- | --- | --- | --- | --- | --- | --- |
| PostgreSQL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MySQL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MongoDB | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Firestore | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Se agregó desde entonces: adendas, corrección de datos y alergias, citas en los cuatro
motores, pediatría (crecimiento y vacunación), laboratorio (órdenes, resultados,
validación), integridad del hospital (PostgreSQL `010`), auditoría y `/health/ready`.
La Clínica Odontológica quedó completa frente al mockup y probada contra Firestore real,
concurrencia incluida ([contrato](contrato_clinica_odontologica.md)). El arranque desde
cero con Docker ya se comprobó. Detalle en [documentacion-backend.md](../documentacion-backend.md).

## Frontend

HTML/JS sencillo servido por FastAPI en `/app/`, sin compilación. Detalle por institución en
[frontend.md](frontend.md).

| Módulo | Estado |
| --- | --- |
| Acceso, cambio de contraseña y administración (superusuario y por institución) | ✅ |
| Clínica Odontológica: pacientes, historial, agenda, odontograma, secretaria | ✅ |
| Centro Pediátrico: pacientes, crecimiento, vacunación, tutores, agenda, facturación | ✅ |
| Hospital General: inicio, pacientes, emergencias, camas, ingresos, atenciones, agenda, pagos | ✅ |
| Laboratorio Clínico: tablero de órdenes, muestras, resultados, validación, catálogo | ✅ |

Lo que pide el PDF (iniciar sesión, ver la información ordenada **sin que la interfaz cambie
según el motor**, registrar pacientes, consultas con diagnósticos, tratamientos y recetas, y
archivar historiales) está cubierto en las cuatro instituciones: registro, ficha, historial y
consultas son las mismas pantallas para todos los motores.

El Hospital y el Laboratorio se recorrieron completos contra el backend real en Docker (ingreso,
cobro, alta y limpieza de cama; orden, muestra, resultados, validación y cancelación) y se
revisaron en móvil (390 px) sin desplazamiento horizontal. Lo que queda es el documento
comparativo.

## Documento comparativo (pendiente de redactar)

Ya existe material en `modelo_laboratorio.md`, `revision_mysql.md`,
`modelo_odontologia.md`, `decision_firestore.md` e `identidad_central.md`. Falta:

- La justificación formal de cada asignación institución ↔ motor (volumen,
  estructura y necesidad de transacciones).
- La sección de PostgreSQL.
- La comparación final de consistencia y seguridad.
