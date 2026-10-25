-- Centro Pediatrico: tutores del paciente desde la API.
-- Un historial archivado no admite tutores nuevos ni cambios en sus vinculos (la base lo
-- impone aunque se salte la API). El principal unico y "principal => autorizado" ya los
-- garantizan uq_tutor_principal y ck_tutor_principal de 001.
-- Idempotente. Aplicar a mano en una base existente (PowerShell, desde la raiz); despues 014:
--   Get-Content database\mysql\013_tutores.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
USE hospital_pediatrico;
DROP TRIGGER IF EXISTS paciente_tutor_insert;
DROP TRIGGER IF EXISTS paciente_tutor_update;
DELIMITER $$
CREATE TRIGGER paciente_tutor_insert BEFORE INSERT ON paciente_tutor FOR EACH ROW
BEGIN
  DECLARE baja BOOLEAN;
  SELECT archivado INTO baja FROM paciente WHERE id_paciente = NEW.id_paciente FOR SHARE;
  IF baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
END$$
CREATE TRIGGER paciente_tutor_update BEFORE UPDATE ON paciente_tutor FOR EACH ROW
BEGIN
  DECLARE baja BOOLEAN;
  IF NEW.id_paciente <> OLD.id_paciente OR NEW.id_tutor <> OLD.id_tutor THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Un vinculo de tutor no se reasigna';
  END IF;
  SELECT archivado INTO baja FROM paciente WHERE id_paciente = NEW.id_paciente FOR SHARE;
  IF baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
END$$
DELIMITER ;
