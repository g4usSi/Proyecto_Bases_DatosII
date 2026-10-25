-- Permisos minimos de la cuenta de la API para el modulo pediatrico. Aplicar DESPUES de 008.
-- Sin DELETE. Los controles solo se agregan; el catalogo de vacunas y sus lotes se cargan
-- con la cuenta administrativa (la API solo los lee, y nunca ve el precio).
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\mysql\009_permisos_pediatria.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
GRANT SELECT, INSERT ON hospital_pediatrico.control_crecimiento TO 'historiales_app'@'%';
GRANT SELECT ON hospital_pediatrico.nombre_vacuna TO 'historiales_app'@'%';
GRANT SELECT (id_vacuna, nombre_vacuna_fk, lote_vacuna, fabricante, fecha_ingreso,
              fecha_vencimiento, cantidad)
  ON hospital_pediatrico.catalogo_vacunas TO 'historiales_app'@'%';
GRANT SELECT, INSERT ON hospital_pediatrico.esquema_vacunacion TO 'historiales_app'@'%';
-- Programar inserta; aplicar o cancelar solo toca estas columnas (el trigger 002 descuenta
-- la existencia del lote con los privilegios de quien lo creo, no los de la API).
GRANT UPDATE (estado_aplicacion, id_vacuna_fk, fecha_aplicacion, id_medico_aplicador,
              observaciones_reaccion)
  ON hospital_pediatrico.esquema_vacunacion TO 'historiales_app'@'%';
