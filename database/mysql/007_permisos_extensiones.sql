-- Permisos minimos de la cuenta de la API para lo que agrega 006 (citas, adendas y
-- correccion de datos). Sin DELETE en ninguna tabla. Aplicar DESPUES de 006.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\mysql\007_permisos_extensiones.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
GRANT SELECT, INSERT ON hospital_pediatrico.cita TO 'historiales_app'@'%';
GRANT UPDATE (estado, motivo_cambio, actualizada_por)
  ON hospital_pediatrico.cita TO 'historiales_app'@'%';
-- Solo se agregan notas (adenda); el trigger consulta_notas_solo_agregar impide reescribirlas.
GRANT UPDATE (notas_medicas) ON hospital_pediatrico.consulta_medica TO 'historiales_app'@'%';
GRANT UPDATE (nombre, apellido, fecha_nacimiento, telefono, correo_electronico, direccion,
              alergias_evaluadas)
  ON hospital_pediatrico.paciente TO 'historiales_app'@'%';
-- La agenda muestra nombre y apellido del medico; nunca salario ni colegiado.
GRANT SELECT (nombre, apellido) ON hospital_pediatrico.medico TO 'historiales_app'@'%';
