-- La imagen crea la cuenta; esta etapa de la API solo implementa lectura.
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'historiales_app'@'%';
GRANT SELECT ON hospital_pediatrico.paciente TO 'historiales_app'@'%';
