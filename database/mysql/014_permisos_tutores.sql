-- Permisos de la API para los tutores (013). Sin DELETE: un tutor que ya no puede recoger
-- al paciente se marca como no autorizado, no se borra.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\mysql\014_permisos_tutores.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
GRANT SELECT (id_tutor, nombre, apellido, dpi_pasaporte, telefono, correo_electronico, direccion),
  INSERT (nombre, apellido, dpi_pasaporte, telefono, correo_electronico, direccion),
  UPDATE (telefono, correo_electronico, direccion)
  ON hospital_pediatrico.tutor TO 'historiales_app'@'%';
GRANT SELECT, INSERT ON hospital_pediatrico.paciente_tutor TO 'historiales_app'@'%';
GRANT UPDATE (parentesco, es_principal, autorizado)
  ON hospital_pediatrico.paciente_tutor TO 'historiales_app'@'%';
