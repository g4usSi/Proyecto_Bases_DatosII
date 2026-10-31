# Avance de la Entrega II (estimado al 31 de octubre de 2026)

Estimación del equipo contra los "Resultados esperados" del PDF. Los pesos son
propios, no de la rúbrica; actualizar esta tabla cuando cambie el estado.

## Resumen

| Parte | Avance |
| --- | --- |
| Backend (API + motores) | **≈ 98 %** |
| Frontend (cliente) | **0 %**: tecnología decidida (HTML/JS en FastAPI) y mockup listo; cliente sin construir |
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

Se agregó desde entonces: adendas, corrección de datos y alergias, citas en los cuatro
motores, pediatría (crecimiento y vacunación), laboratorio (órdenes, resultados,
validación), integridad del hospital (PostgreSQL `010`), auditoría y `/health/ready`.
La Clínica Odontológica quedó completa frente al mockup y probada contra Firestore real,
concurrencia incluida ([contrato](contrato_clinica_odontologica.md)). Lo que falta del backend:
probar el arranque con Docker. Detalle en [documentacion-backend.md](../documentacion-backend.md).

## Frontend (pendiente completo)

Decisión: HTML/JS sencillo servido por FastAPI. Mockup en `referencia/`; plan, pantallas por
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
