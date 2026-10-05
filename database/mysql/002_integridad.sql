USE hospital_pediatrico;
DELIMITER $$

CREATE TRIGGER paciente_fecha_insert BEFORE INSERT ON paciente FOR EACH ROW
BEGIN
  IF NEW.fecha_nacimiento > CURRENT_DATE THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La fecha de nacimiento no puede ser futura';
  END IF;
END$$
CREATE TRIGGER paciente_fecha_update BEFORE UPDATE ON paciente FOR EACH ROW
BEGIN
  IF NEW.fecha_nacimiento > CURRENT_DATE THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'La fecha de nacimiento no puede ser futura';
  END IF;
END$$

CREATE TRIGGER consulta_validar_insert BEFORE INSERT ON consulta_medica FOR EACH ROW
BEGIN
  DECLARE baja BOOLEAN;
  DECLARE medico_activo BOOLEAN;
  DECLARE nacimiento DATE;
  -- Mismo registro bloqueado al archivar: evita insertar contra una baja concurrente.
  SELECT archivado, fecha_nacimiento INTO baja, nacimiento FROM paciente
    WHERE id_paciente = NEW.id_paciente FOR UPDATE;
  SELECT activo INTO medico_activo FROM medico WHERE id_medico = NEW.id_medico FOR SHARE;
  IF baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
  IF NOT medico_activo THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El medico esta inactivo'; END IF;
  IF DATE(NEW.fecha_hora) < nacimiento THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Consulta anterior al nacimiento';
  END IF;
END$$
CREATE TRIGGER consulta_identidad_inmutable BEFORE UPDATE ON consulta_medica FOR EACH ROW
BEGIN
  IF NEW.id_paciente <> OLD.id_paciente OR NEW.id_medico <> OLD.id_medico THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No reasignar la identidad de una consulta historica';
  END IF;
END$$

CREATE TRIGGER vacuna_aplicar_insert BEFORE INSERT ON esquema_vacunacion FOR EACH ROW
BEGIN
  DECLARE baja BOOLEAN;
  DECLARE medico_activo BOOLEAN;
  SELECT archivado INTO baja FROM paciente WHERE id_paciente = NEW.id_paciente_fk FOR UPDATE;
  IF baja THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El expediente esta archivado'; END IF;
  IF NEW.estado_aplicacion = 'Aplicada' THEN
    SELECT activo INTO medico_activo FROM medico WHERE id_medico = NEW.id_medico_aplicador FOR SHARE;
    IF NOT medico_activo THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'El aplicador esta inactivo'; END IF;
    UPDATE catalogo_vacunas SET cantidad = cantidad - 1
      WHERE id_vacuna = NEW.id_vacuna_fk AND nombre_vacuna_fk = NEW.id_nombre_vacuna_fk
        AND cantidad > 0 AND DATE(NEW.fecha_aplicacion) BETWEEN fecha_ingreso AND fecha_vencimiento;
    IF ROW_COUNT() <> 1 THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Lote incorrecto, vencido o sin existencias';
    END IF;
  END IF;
END$$
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
    UPDATE catalogo_vacunas SET cantidad = cantidad - 1
      WHERE id_vacuna = NEW.id_vacuna_fk AND nombre_vacuna_fk = NEW.id_nombre_vacuna_fk
        AND cantidad > 0 AND DATE(NEW.fecha_aplicacion) BETWEEN fecha_ingreso AND fecha_vencimiento;
    IF ROW_COUNT() <> 1 THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Lote incorrecto, vencido o sin existencias';
    END IF;
  END IF;
END$$
CREATE TRIGGER vacuna_conservar_delete BEFORE DELETE ON esquema_vacunacion FOR EACH ROW
BEGIN
  IF OLD.estado_aplicacion = 'Aplicada' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No borrar aplicaciones historicas';
  END IF;
END$$

-- UPDATE de la cabecera adquiere un bloqueo de fila y usa el saldo mas reciente.
-- CHECK total_pagado <= total_facturado rechaza sobrepagos y rebajas bajo lo ya pagado.
-- Todos estos cambios se revierten junto a la sentencia/TRANSACCION si hay error.
-- Bloquear ANTES del INSERT evita que dos FKs tomen un bloqueo compartido y
-- compitan luego por convertirlo en exclusivo dentro del trigger AFTER.
CREATE TRIGGER detalle_bloquear_insert BEFORE INSERT ON detalle_facturacion FOR EACH ROW
BEGIN
  DECLARE factura INT;
  SELECT id_facturacion INTO factura FROM facturacion
    WHERE id_facturacion = NEW.id_facturacion FOR UPDATE;
END$$
CREATE TRIGGER pago_bloquear_insert BEFORE INSERT ON pago FOR EACH ROW
BEGIN
  DECLARE factura INT;
  SELECT id_facturacion INTO factura FROM facturacion
    WHERE id_facturacion = NEW.id_facturacion FOR UPDATE;
END$$
CREATE TRIGGER detalle_total_insert AFTER INSERT ON detalle_facturacion FOR EACH ROW
BEGIN
  UPDATE facturacion SET total_facturado = total_facturado + NEW.monto
    WHERE id_facturacion = NEW.id_facturacion;
END$$
CREATE TRIGGER detalle_total_update BEFORE UPDATE ON detalle_facturacion FOR EACH ROW
BEGIN
  IF NEW.id_facturacion <> OLD.id_facturacion THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No trasladar cargos entre facturas';
  END IF;
END$$
CREATE TRIGGER detalle_total_actualizar AFTER UPDATE ON detalle_facturacion FOR EACH ROW
BEGIN
  UPDATE facturacion SET total_facturado = total_facturado - OLD.monto + NEW.monto
    WHERE id_facturacion = NEW.id_facturacion;
END$$
CREATE TRIGGER detalle_total_delete AFTER DELETE ON detalle_facturacion FOR EACH ROW
BEGIN
  UPDATE facturacion SET total_facturado = total_facturado - OLD.monto
    WHERE id_facturacion = OLD.id_facturacion;
END$$
CREATE TRIGGER pago_total_insert AFTER INSERT ON pago FOR EACH ROW
BEGIN
  UPDATE facturacion SET total_pagado = total_pagado + NEW.monto
    WHERE id_facturacion = NEW.id_facturacion;
END$$
CREATE TRIGGER pago_total_update BEFORE UPDATE ON pago FOR EACH ROW
BEGIN
  IF NEW.id_facturacion <> OLD.id_facturacion THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'No trasladar pagos entre facturas';
  END IF;
END$$
CREATE TRIGGER pago_total_actualizar AFTER UPDATE ON pago FOR EACH ROW
BEGIN
  UPDATE facturacion SET total_pagado = total_pagado - OLD.monto + NEW.monto
    WHERE id_facturacion = NEW.id_facturacion;
END$$
CREATE TRIGGER pago_total_delete AFTER DELETE ON pago FOR EACH ROW
BEGIN
  UPDATE facturacion SET total_pagado = total_pagado - OLD.monto
    WHERE id_facturacion = OLD.id_facturacion;
END$$
DELIMITER ;
