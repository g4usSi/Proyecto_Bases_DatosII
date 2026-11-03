-- Centro Pediatrico: facturacion como la muestra el frontend (mockup "Facturacion").
--   * Anular una factura: queda registrada como anulada (no se borra). Solo sin pagos, y ya
--     no admite cargos ni pagos. No se puede "desanular".
--   * Factura a nombre del tutor: id_tutor_fk guarda a quien se facturo (por defecto el tutor
--     principal al emitirla). Debe ser un tutor vinculado al paciente de la consulta; se
--     conserva aunque despues cambie el tutor principal.
-- Aditivo e idempotente. Aplicar DESPUES de 002 y 013, y luego 016 (PowerShell, desde la raiz):
--   Get-Content database\mysql\015_facturacion_anular_tutor.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
USE hospital_pediatrico;
DELIMITER $$

-- MySQL no tiene ADD COLUMN IF NOT EXISTS: este ayudante lo emula y se elimina al final.
DROP PROCEDURE IF EXISTS agregar_columna$$
CREATE PROCEDURE agregar_columna(IN tabla VARCHAR(64), IN columna VARCHAR(64), IN definicion TEXT)
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tabla AND COLUMN_NAME = columna
  ) THEN
    SET @ddl = CONCAT('ALTER TABLE `', tabla, '` ADD COLUMN `', columna, '` ', definicion);
    PREPARE sentencia FROM @ddl;
    EXECUTE sentencia;
    DEALLOCATE PREPARE sentencia;
  END IF;
END$$

DROP PROCEDURE IF EXISTS agregar_restriccion$$
CREATE PROCEDURE agregar_restriccion(IN tabla VARCHAR(64), IN nombre VARCHAR(64), IN definicion TEXT)
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = tabla AND CONSTRAINT_NAME = nombre
  ) THEN
    SET @ddl = CONCAT('ALTER TABLE `', tabla, '` ADD CONSTRAINT `', nombre, '` ', definicion);
    PREPARE sentencia FROM @ddl;
    EXECUTE sentencia;
    DEALLOCATE PREPARE sentencia;
  END IF;
END$$
DELIMITER ;

CALL agregar_columna('facturacion', 'anulada_en', 'DATETIME(6) NULL');
CALL agregar_columna('facturacion', 'id_tutor_fk', 'INT NULL');
-- Anular exige no tener pagos (total_pagado lo mantienen los triggers de 002).
CALL agregar_restriccion('facturacion', 'ck_fact_anulada_sin_pagos',
  'CHECK (anulada_en IS NULL OR total_pagado = 0)');
CALL agregar_restriccion('facturacion', 'fk_fact_tutor',
  'FOREIGN KEY (id_tutor_fk) REFERENCES tutor(id_tutor)');
DROP PROCEDURE agregar_columna;
DROP PROCEDURE agregar_restriccion;

DROP TRIGGER IF EXISTS detalle_bloquear_insert;
DROP TRIGGER IF EXISTS pago_bloquear_insert;
DROP TRIGGER IF EXISTS facturacion_validar_insert;
DROP TRIGGER IF EXISTS facturacion_validar_update;
DELIMITER $$
-- Mismo bloqueo de 002 (serializa cargos y pagos de una factura) y, ademas, una factura
-- anulada ya no admite movimientos.
CREATE TRIGGER detalle_bloquear_insert BEFORE INSERT ON detalle_facturacion FOR EACH ROW
BEGIN
  DECLARE anulada DATETIME(6);
  SELECT anulada_en INTO anulada FROM facturacion
    WHERE id_facturacion = NEW.id_facturacion FOR UPDATE;
  IF anulada IS NOT NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La factura esta anulada';
  END IF;
END$$
CREATE TRIGGER pago_bloquear_insert BEFORE INSERT ON pago FOR EACH ROW
BEGIN
  DECLARE anulada DATETIME(6);
  SELECT anulada_en INTO anulada FROM facturacion
    WHERE id_facturacion = NEW.id_facturacion FOR UPDATE;
  IF anulada IS NOT NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La factura esta anulada';
  END IF;
END$$

-- El tutor facturado debe estar vinculado al paciente de la consulta.
CREATE TRIGGER facturacion_validar_insert BEFORE INSERT ON facturacion FOR EACH ROW
BEGIN
  IF NEW.anulada_en IS NOT NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Una factura nueva no puede nacer anulada';
  END IF;
  IF NEW.id_tutor_fk IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM paciente_tutor pt JOIN consulta_medica c ON c.id_paciente = pt.id_paciente
    WHERE c.id_consulta = NEW.id_consulta_fk AND pt.id_tutor = NEW.id_tutor_fk
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El tutor no esta vinculado al paciente';
  END IF;
END$$
-- Anular es definitivo y el titular no cambia despues de emitir la factura.
CREATE TRIGGER facturacion_validar_update BEFORE UPDATE ON facturacion FOR EACH ROW
BEGIN
  IF OLD.anulada_en IS NOT NULL AND NOT (NEW.anulada_en <=> OLD.anulada_en) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Una factura anulada no se reabre';
  END IF;
  IF NOT (NEW.id_tutor_fk <=> OLD.id_tutor_fk) OR NEW.id_consulta_fk <> OLD.id_consulta_fk THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No cambiar el titular ni la consulta de una factura';
  END IF;
END$$
DELIMITER ;
