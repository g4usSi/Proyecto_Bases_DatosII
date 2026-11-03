-- Permisos de la API para la facturacion de 015: emitir la factura a nombre de un tutor y
-- marcarla como anulada. Sigue sin DELETE ni cambios de montos (los mantienen triggers).
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\mysql\016_permisos_facturacion.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
GRANT UPDATE (anulada_en) ON hospital_pediatrico.facturacion TO 'historiales_app'@'%';
