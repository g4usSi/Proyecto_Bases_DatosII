-- La imagen crea la cuenta; aqui se parte sin privilegios. Los de escritura estan en 005.
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'historiales_app'@'%';
GRANT SELECT ON hospital_pediatrico.paciente TO 'historiales_app'@'%';
