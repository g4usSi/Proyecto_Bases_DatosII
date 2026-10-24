# Avance de la Entrega II (estimado al 23 de octubre de 2026)

Estimación del equipo contra los "Resultados esperados" del PDF. Los pesos son
propios, no de la rúbrica; actualizar esta tabla cuando cambie el estado.

## Resumen

| Parte | Avance |
| --- | --- |
| Backend (API + motores) | **≈ 63 %** |
| Frontend (cliente) | **0 %**: tecnología decidida (HTML/JS en FastAPI), faltan mockups |
| Documento comparativo | **≈ 30 %**: el material está repartido en `docs/`, sin redactar |
| Entrega II completa (backend 50 %, frontend 30 %, documento 20 %) | **≈ 37 %** |

## Backend

| Área (peso) | Avance | Detalle |
| --- | --- | --- |
| Base común (20 %) | 95 % | FastAPI hexagonal, login JWT, enrutamiento por usuario, permisos, roles, Docker. |
| Modelo por motor (20 %) | 85 % | Firestore 100 %. MySQL y MongoDB 85 %. PostgreSQL 70 % (reglas pendientes del SQL original). |
| Operaciones comunes en 4 motores (40 %) | 40 % | 8 de 20: Firestore 5/5; PostgreSQL, MySQL y MongoDB solo leen paciente. |
| Consistencia demostrada (10 %) | 50 % | Firestore: transacciones. MySQL: triggers probados. PostgreSQL: parcial. MongoDB necesita replica set para escribir varias colecciones. |
| Pruebas (10 %) | 60 % | Unitarias de todas las rutas. Integración: lectura en 4 motores y Firestore completo. |

Operaciones por motor (✅ hecho, — pendiente):

| | Registrar | Leer | Historial | Consulta + diagnóstico + receta | Archivar |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL | — | ✅ | — | — | — |
| MySQL | — | ✅ | — | — | — |
| MongoDB | — | ✅ | — | — | — |
| Firestore | ✅ | ✅ | ✅ | ✅ | ✅ |

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
