-- Facturacion pediatrica desde la API: abrir facturas, agregar cargos y registrar pagos.
-- Los totales los actualizan los triggers de 002 (con privilegios de su definidor); la
-- cuenta de la API solo inserta y lee. Sin UPDATE ni DELETE: un pago no se edita.
-- Aplicar despues de 003-011. Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\mysql\012_permisos_cobros.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
GRANT SELECT, INSERT ON hospital_pediatrico.facturacion TO 'historiales_app'@'%';
GRANT SELECT, INSERT ON hospital_pediatrico.detalle_facturacion TO 'historiales_app'@'%';
GRANT SELECT, INSERT ON hospital_pediatrico.pago TO 'historiales_app'@'%';
GRANT SELECT ON hospital_pediatrico.tipo_de_pago TO 'historiales_app'@'%';
