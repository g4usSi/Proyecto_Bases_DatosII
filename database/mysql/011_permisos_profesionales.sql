-- La API vincula el perfil local (tabla medico) de un profesional dado de alta o cambiado
-- desde la administracion de profesionales. Solo nombres y estado; nunca salario.
-- Aplicar despues de 003-010. Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\mysql\011_permisos_profesionales.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
GRANT INSERT (id_profesional_central, nombre, apellido, colegiado, activo)
  ON hospital_pediatrico.medico TO 'historiales_app'@'%';
GRANT UPDATE (nombre, apellido, activo) ON hospital_pediatrico.medico TO 'historiales_app'@'%';
