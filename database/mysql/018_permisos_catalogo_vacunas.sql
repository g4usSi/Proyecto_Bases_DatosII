-- Permisos de la API para que el administrador del Centro Pediatrico mantenga el catalogo
-- de tipos de vacuna: agregar vacunas y corregir su descripcion. Sin DELETE ni cambio de
-- nombre: los esquemas de los pacientes ya apuntan a esas vacunas.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\mysql\018_permisos_catalogo_vacunas.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
GRANT INSERT (nombre, enfermedades_que_previene, edad_recomendada_meses, dosis_sugerida),
  UPDATE (enfermedades_que_previene, edad_recomendada_meses, dosis_sugerida)
  ON hospital_pediatrico.nombre_vacuna TO 'historiales_app'@'%';
