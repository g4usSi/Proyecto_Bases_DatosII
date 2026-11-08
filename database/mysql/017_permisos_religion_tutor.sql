-- Permisos de la API para la religion (opcional) del tutor. El esquema ya la traia desde 001:
-- el catalogo `religion` y la llave tutor.id_religion_fk. La API busca la religion por nombre
-- y, si es nueva, la agrega al catalogo; no la borra ni la renombra.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\mysql\017_permisos_religion_tutor.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
GRANT SELECT (id_religion, nombre), INSERT (nombre)
  ON hospital_pediatrico.religion TO 'historiales_app'@'%';
GRANT SELECT (id_religion_fk), INSERT (id_religion_fk), UPDATE (id_religion_fk)
  ON hospital_pediatrico.tutor TO 'historiales_app'@'%';
