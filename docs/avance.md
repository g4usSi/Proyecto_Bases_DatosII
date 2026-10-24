# Avance de la Entrega II (estimado al 23 de octubre de 2026)

Estimación del equipo contra los "Resultados esperados" del PDF. Los pesos son
propios, no de la rúbrica; actualizar esta tabla cuando cambie el estado.

## Resumen

| Parte | Avance |
| --- | --- |
| Backend (API + motores) | **≈ 93 %** |
| Frontend (cliente) | **0 %**: tecnología decidida (HTML/JS en FastAPI), faltan mockups |
| Documento comparativo | **≈ 30 %**: el material está repartido en `docs/`, sin redactar |
| Entrega II completa (backend 50 %, frontend 30 %, documento 20 %) | **≈ 52 %** |

## Backend

| Área (peso) | Avance | Detalle |
| --- | --- | --- |
| Base común (20 %) | 95 % | FastAPI hexagonal, login JWT, enrutamiento por usuario, permisos, roles, Docker. |
| Modelo por motor (20 %) | 85 % | Firestore 100 %. MySQL y MongoDB 90 %. PostgreSQL 70 % (reglas pendientes del SQL original: pagos, camas, cita/atención). |
| Operaciones comunes en 4 motores (40 %) | 100 % | 20 de 20 (5 operaciones × 4 motores) más búsqueda por nombre. Citas y odontograma solo en Firestore (extra de la clínica). |
| Consistencia demostrada (10 %) | 85 % | Pruebas de concurrencia (dos bajas, consulta vs. baja) en PostgreSQL, MySQL, MongoDB y Firestore. MongoDB: sin transacciones (servidor único); queda una ventana de milisegundos documentada. |
| Pruebas (10 %) | 85 % | Unitarias de todas las rutas. Integración real por motor (datos sintéticos, cuenta limitada de la API, flujo completo con login). Faltan pruebas en contenedores nuevos desde cero (Docker). |

Operaciones por motor (✅ hecho, — pendiente):

| | Registrar | Leer | Buscar | Historial | Consulta + diagnóstico + receta | Archivar |
| --- | --- | --- | --- | --- | --- | --- |
| PostgreSQL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MySQL | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MongoDB | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Firestore | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Lo que falta del backend: citas en los otros tres motores (la clínica es la que agenda),
las reglas pendientes del SQL original de PostgreSQL, auditoría/rectificación clínica y
probar el arranque desde cero con Docker (los scripts nuevos se probaron en motores locales
equivalentes).

## Frontend (pendiente completo)

Decisión: HTML/JS sencillo servido por FastAPI. Faltan los mockups; plan, pantallas por
rol y odontograma en [frontend.md](frontend.md).

Lo que pide el PDF: un cliente que permita iniciar sesión, ver toda la información de forma
ordenada **sin que la interfaz cambie según el motor**, registrar pacientes, agregar consultas,
diagnósticos, tratamientos y recetas, y archivar historiales. Para la clínica también
hacen falta la agenda de citas y el odontograma. La API ya expone todo esto en `/docs`.

## Documento comparativo (pendiente de redactar)

Ya existe material en `modelo_laboratorio.md`, `revision_mysql.md`,
`modelo_odontologia.md`, `decision_firestore.md` e `identidad_central.md`. Falta:

- La justificación formal de cada asignación institución ↔ motor (volumen,
  estructura y necesidad de transacciones).
- La sección de PostgreSQL.
- La comparación final de consistencia y seguridad.
