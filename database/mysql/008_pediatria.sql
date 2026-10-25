-- Reglas de integridad del modulo pediatrico (controles de crecimiento).
-- Aplicar DESPUES de 002 (el esquema de vacunacion ya esta protegido por sus triggers).
-- Idempotente: se puede ejecutar de nuevo.
USE hospital_pediatrico;
DELIMITER $$

DROP TRIGGER IF EXISTS control_validar_insert$$
CREATE TRIGGER control_validar_insert BEFORE INSERT ON control_crecimiento FOR EACH ROW
BEGIN
  DECLARE baja BOOLEAN;
  DECLARE nacimiento DATE;
  -- Mismo bloqueo que la baja del expediente: no se inserta contra un archivado concurrente.
  SELECT archivado, fecha_nacimiento INTO baja, nacimiento FROM paciente
    WHERE id_paciente = NEW.id_paciente_fk FOR SHARE;
  IF baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
  IF DATE(NEW.fecha_registro) < nacimiento THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Control anterior al nacimiento';
  END IF;
END$$

-- Un control es un hecho medido ese dia: no se reescribe ni cambia de paciente.
DROP TRIGGER IF EXISTS control_inmutable$$
CREATE TRIGGER control_inmutable BEFORE UPDATE ON control_crecimiento FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Un control de crecimiento no se modifica';
END$$

-- Las dosis aplicadas ya estan protegidas por 002; aqui se impide borrar controles.
DROP TRIGGER IF EXISTS control_conservar_delete$$
CREATE TRIGGER control_conservar_delete BEFORE DELETE ON control_crecimiento FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No borrar controles de crecimiento';
END$$

DELIMITER ;
