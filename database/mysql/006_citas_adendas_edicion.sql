-- Centro Pediatrico: agenda de citas sin choques, adendas a consultas (solo agregar) y
-- correccion de datos del paciente. Aditivo: no borra ni cambia datos existentes.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz); despues aplicar tambien 007:
--   Get-Content database\mysql\006_citas_adendas_edicion.sql | docker compose exec -T mysql sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" hospital_pediatrico'
-- Es idempotente: se puede aplicar mas de una vez.
USE hospital_pediatrico;

-- Las fechas se guardan en UTC (la conexion de la API usa time_zone '+00:00').
CREATE TABLE IF NOT EXISTS cita (
  id_cita INT AUTO_INCREMENT PRIMARY KEY,
  id_paciente INT NOT NULL,
  id_medico INT NOT NULL,
  inicio DATETIME(6) NOT NULL,
  duracion_minutos INT NOT NULL,
  fin DATETIME(6) GENERATED ALWAYS AS (DATE_ADD(inicio, INTERVAL duracion_minutos MINUTE)) STORED,
  motivo VARCHAR(300) NOT NULL,
  estado VARCHAR(20) NOT NULL DEFAULT 'programada',
  creada_por CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
    COMMENT 'Restringido: identidad central de quien agendo',
  creada_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  motivo_cambio VARCHAR(300) NULL,
  actualizada_por CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL,
  CONSTRAINT fk_cita_paciente FOREIGN KEY(id_paciente) REFERENCES paciente(id_paciente),
  CONSTRAINT fk_cita_medico FOREIGN KEY(id_medico) REFERENCES medico(id_medico),
  CONSTRAINT ck_cita_estado CHECK (
    estado IN ('programada','confirmada','atendida','cancelada','no_asistio')),
  CONSTRAINT ck_cita_duracion CHECK (duracion_minutos BETWEEN 5 AND 480),
  CONSTRAINT ck_cita_motivo CHECK (CHAR_LENGTH(TRIM(motivo)) > 0),
  INDEX ix_cita_medico(id_medico, inicio),
  INDEX ix_cita_paciente(id_paciente, inicio)
) ENGINE=InnoDB;

DELIMITER $$

-- Citas sin choques: MySQL no tiene restriccion de exclusion, asi que el trigger bloquea la
-- fila del medico (las agendas de un mismo medico se validan de una en una) y revisa el cruce.
-- La revision usa lectura con bloqueo (FOR SHARE): una lectura normal veria la "foto" de la
-- transaccion y no las citas que otra secretaria acaba de confirmar.
DROP TRIGGER IF EXISTS cita_validar_insert$$
CREATE TRIGGER cita_validar_insert BEFORE INSERT ON cita FOR EACH ROW
BEGIN
  DECLARE v_baja BOOLEAN;
  DECLARE v_activo BOOLEAN;
  DECLARE v_choques INT;
  SELECT archivado INTO v_baja FROM paciente WHERE id_paciente = NEW.id_paciente FOR SHARE;
  SELECT activo INTO v_activo FROM medico WHERE id_medico = NEW.id_medico FOR UPDATE;
  IF v_baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
  IF NOT v_activo THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El medico esta inactivo'; END IF;
  SELECT COUNT(*) INTO v_choques FROM cita
    WHERE id_medico = NEW.id_medico AND estado IN ('programada','confirmada')
      AND inicio < DATE_ADD(NEW.inicio, INTERVAL NEW.duracion_minutos MINUTE)
      AND NEW.inicio < fin FOR SHARE;
  IF v_choques > 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Horario ocupado: el medico ya tiene una cita';
  END IF;
END$$

DROP TRIGGER IF EXISTS cita_validar_update$$
CREATE TRIGGER cita_validar_update BEFORE UPDATE ON cita FOR EACH ROW
BEGIN
  IF NEW.id_paciente <> OLD.id_paciente OR NEW.id_medico <> OLD.id_medico
     OR NEW.inicio <> OLD.inicio OR NEW.duracion_minutos <> OLD.duracion_minutos THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'Una cita no se reasigna ni se reprograma: cancela y agenda otra';
  END IF;
  IF OLD.estado IN ('cancelada','atendida','no_asistio') AND NEW.estado <> OLD.estado THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Una cita finalizada ya no cambia de estado';
  END IF;
END$$

-- Adendas: las notas de una consulta solo crecen por el final y su identidad no cambia.
-- (BINARY: la colacion del esquema ignora acentos y mayusculas, y aqui debe ser exacto.)
DROP TRIGGER IF EXISTS consulta_notas_solo_agregar$$
CREATE TRIGGER consulta_notas_solo_agregar BEFORE UPDATE ON consulta_medica FOR EACH ROW
BEGIN
  IF NEW.fecha_hora <> OLD.fecha_hora OR BINARY NEW.motivo_consulta <> BINARY OLD.motivo_consulta THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No se reescribe una consulta historica';
  END IF;
  IF OLD.notas_medicas IS NOT NULL AND OLD.notas_medicas <> '' AND (
       NEW.notas_medicas IS NULL
       OR BINARY LEFT(NEW.notas_medicas, CHAR_LENGTH(OLD.notas_medicas)) <> BINARY OLD.notas_medicas) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Las notas solo admiten adendas al final';
  END IF;
END$$

-- Tampoco se agregan diagnosticos, tratamientos ni recetas en un historial archivado.
DROP TRIGGER IF EXISTS diag_paciente_activo$$
CREATE TRIGGER diag_paciente_activo BEFORE INSERT ON consulta_diagnostico FOR EACH ROW
BEGIN
  DECLARE v_baja BOOLEAN;
  SELECT p.archivado INTO v_baja FROM consulta_medica c
    JOIN paciente p ON p.id_paciente = c.id_paciente
    WHERE c.id_consulta = NEW.id_consulta FOR SHARE;
  IF v_baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
END$$
DROP TRIGGER IF EXISTS trat_paciente_activo$$
CREATE TRIGGER trat_paciente_activo BEFORE INSERT ON consulta_tratamiento FOR EACH ROW
BEGIN
  DECLARE v_baja BOOLEAN;
  SELECT p.archivado INTO v_baja FROM consulta_medica c
    JOIN paciente p ON p.id_paciente = c.id_paciente
    WHERE c.id_consulta = NEW.id_consulta FOR SHARE;
  IF v_baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
END$$
DROP TRIGGER IF EXISTS receta_paciente_activo$$
CREATE TRIGGER receta_paciente_activo BEFORE INSERT ON recetas_medicamento FOR EACH ROW
BEGIN
  DECLARE v_baja BOOLEAN;
  SELECT p.archivado INTO v_baja FROM consulta_medica c
    JOIN paciente p ON p.id_paciente = c.id_paciente
    WHERE c.id_consulta = NEW.id_consulta FOR SHARE;
  IF v_baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
END$$

-- Correccion de datos del paciente: solo mientras el historial esta activo.
DROP TRIGGER IF EXISTS paciente_archivado_inmutable$$
CREATE TRIGGER paciente_archivado_inmutable BEFORE UPDATE ON paciente FOR EACH ROW
BEGIN
  IF OLD.archivado AND (
       BINARY NEW.nombre <> BINARY OLD.nombre OR BINARY NEW.apellido <> BINARY OLD.apellido
       OR NEW.fecha_nacimiento <> OLD.fecha_nacimiento
       OR NOT (NEW.telefono <=> OLD.telefono)
       OR NOT (NEW.correo_electronico <=> OLD.correo_electronico)
       OR NOT (NEW.direccion <=> OLD.direccion)
       OR NEW.alergias_evaluadas <> OLD.alergias_evaluadas) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado';
  END IF;
END$$

DELIMITER ;
