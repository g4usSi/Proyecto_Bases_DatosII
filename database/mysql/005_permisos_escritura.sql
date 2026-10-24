-- Permisos minimos de la cuenta de la API para las escrituras de 004.
-- Aplicar DESPUES de 003 y 004. La cuenta NO recibe DELETE ni UPDATE general:
-- un historial clinico no se borra y la unica modificacion permitida es archivarlo.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\mysql\005_permisos_escritura.sql | docker compose exec -T mysql mysql -uroot -p"$env:MYSQL_ROOT_PASSWORD" hospital_pediatrico
GRANT SELECT, INSERT ON hospital_pediatrico.paciente TO 'historiales_app'@'%';
GRANT UPDATE (archivado, fecha_baja, motivo_baja, detalle_baja, archivado_por)
  ON hospital_pediatrico.paciente TO 'historiales_app'@'%';
GRANT SELECT, INSERT ON hospital_pediatrico.alergias_conocidas TO 'historiales_app'@'%';
GRANT SELECT, INSERT ON hospital_pediatrico.paciente_alergia TO 'historiales_app'@'%';
GRANT SELECT, INSERT ON hospital_pediatrico.consulta_medica TO 'historiales_app'@'%';
GRANT SELECT, INSERT ON hospital_pediatrico.consulta_diagnostico TO 'historiales_app'@'%';
GRANT SELECT, INSERT ON hospital_pediatrico.consulta_tratamiento TO 'historiales_app'@'%';
GRANT SELECT, INSERT ON hospital_pediatrico.recetas_medicamento TO 'historiales_app'@'%';
GRANT SELECT ON hospital_pediatrico.estado TO 'historiales_app'@'%';
-- Solo las columnas necesarias; nunca el salario.
GRANT SELECT (id_medico, id_profesional_central, activo)
  ON hospital_pediatrico.medico TO 'historiales_app'@'%';
