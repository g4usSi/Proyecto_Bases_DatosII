-- Decision del equipo: el Centro Pediatrico NO controla existencias por lote desde la API.
-- Aplicar una dosis ya no descuenta stock ni exige un lote; solo registra quien, cuando y
-- las observaciones. La tabla catalogo_vacunas (lotes) se conserva en el esquema pero la API
-- ya no la usa. Aplicar DESPUES de 002 y 008. Idempotente.
--   Get-Content database\mysql\010_sin_stock_vacunas.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
USE hospital_pediatrico;
DELIMITER $$

DROP TRIGGER IF EXISTS vacuna_aplicar_insert$$
CREATE TRIGGER vacuna_aplicar_insert BEFORE INSERT ON esquema_vacunacion FOR EACH ROW
BEGIN
  DECLARE baja BOOLEAN;
  DECLARE medico_activo BOOLEAN;
  SELECT archivado INTO baja FROM paciente WHERE id_paciente = NEW.id_paciente_fk FOR UPDATE;
  IF baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
  IF NEW.estado_aplicacion = 'Aplicada' THEN
    SELECT activo INTO medico_activo FROM medico WHERE id_medico = NEW.id_medico_aplicador FOR SHARE;
    IF NOT medico_activo THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El aplicador esta inactivo'; END IF;
  END IF;
END$$

DROP TRIGGER IF EXISTS vacuna_aplicar_update$$
CREATE TRIGGER vacuna_aplicar_update BEFORE UPDATE ON esquema_vacunacion FOR EACH ROW
BEGIN
  DECLARE baja BOOLEAN;
  DECLARE medico_activo BOOLEAN;
  IF NEW.id_paciente_fk <> OLD.id_paciente_fk THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No reasignar vacunacion a otro paciente';
  END IF;
  IF OLD.estado_aplicacion = 'Aplicada' THEN
    IF NEW.estado_aplicacion <> OLD.estado_aplicacion
      OR NOT (NEW.id_vacuna_fk <=> OLD.id_vacuna_fk)
      OR NEW.id_nombre_vacuna_fk <> OLD.id_nombre_vacuna_fk
      OR NOT (NEW.fecha_aplicacion <=> OLD.fecha_aplicacion)
      OR NOT (NEW.id_medico_aplicador <=> OLD.id_medico_aplicador) THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Aplicacion registrada: requiere rectificacion trazable';
    END IF;
  ELSEIF NEW.estado_aplicacion = 'Aplicada' THEN
    SELECT archivado INTO baja FROM paciente WHERE id_paciente = NEW.id_paciente_fk FOR UPDATE;
    IF baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
    SELECT activo INTO medico_activo FROM medico WHERE id_medico = NEW.id_medico_aplicador FOR SHARE;
    IF NOT medico_activo THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El aplicador esta inactivo'; END IF;
  END IF;
END$$

DROP PROCEDURE IF EXISTS _ajustar_check_vacunacion$$
CREATE PROCEDURE _ajustar_check_vacunacion()
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
             WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'esquema_vacunacion'
               AND CONSTRAINT_NAME = 'ck_esquema_aplicacion') THEN
    ALTER TABLE esquema_vacunacion DROP CHECK ck_esquema_aplicacion;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.TABLE_CONSTRAINTS
                 WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'esquema_vacunacion'
                   AND CONSTRAINT_NAME = 'ck_esquema_aplicacion_v2') THEN
    ALTER TABLE esquema_vacunacion ADD CONSTRAINT ck_esquema_aplicacion_v2 CHECK (
      (estado_aplicacion = 'Aplicada' AND fecha_aplicacion IS NOT NULL
        AND id_medico_aplicador IS NOT NULL)
      OR (estado_aplicacion <> 'Aplicada' AND fecha_aplicacion IS NULL));
  END IF;
END$$
CALL _ajustar_check_vacunacion()$$
DROP PROCEDURE _ajustar_check_vacunacion$$

DELIMITER ;
