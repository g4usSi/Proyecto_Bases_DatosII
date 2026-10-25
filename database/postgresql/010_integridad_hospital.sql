-- Reglas de integridad pendientes del SQL original del Hospital General:
--   * pagos: sin carrera entre pagos simultaneos, sin editar el monto, sin pagar un
--     cobro anulado; el total facturado no puede bajar de lo ya pagado;
--   * camas: una cama no puede tener dos ingresos que se solapen en el tiempo;
--     un paciente tampoco puede estar ingresado en dos camas a la vez;
--   * la atencion que nace de una cita debe ser del mismo paciente.
-- Aditivo e idempotente. No cambia datos.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\postgresql\010_integridad_hospital.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
BEGIN;
SET LOCAL client_min_messages = warning;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------------------
-- PAGOS
-- ---------------------------------------------------------------------------
-- Antes solo se validaba el INSERT y sin bloqueo: dos pagos simultaneos podian pasar
-- cada uno por separado y juntos exceder el total; un UPDATE saltaba la regla.
CREATE OR REPLACE FUNCTION fn_validar_pago_no_excede_total() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_estado_cobro TEXT;
  v_total  NUMERIC(10,2);
  v_pagado NUMERIC(10,2);
BEGIN
  -- Bloquea el cobro: los pagos del mismo cobro se validan de uno en uno.
  SELECT estado INTO v_estado_cobro FROM cobro WHERE id_cobro = NEW.id_cobro FOR UPDATE;

  IF TG_OP = 'UPDATE' THEN
    IF NEW.id_cobro <> OLD.id_cobro OR NEW.id_metodo_pago <> OLD.id_metodo_pago
       OR NEW.monto <> OLD.monto OR NEW.fecha_hora <> OLD.fecha_hora THEN
      RAISE EXCEPTION 'Un pago no se edita: anulalo y registra otro'
        USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.estado = 'Anulado' AND NEW.estado = 'Confirmado' THEN
      RAISE EXCEPTION 'Un pago anulado no se reactiva: registra uno nuevo'
        USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;  -- anular un pago solo reduce lo pagado
  END IF;

  IF NEW.estado = 'Confirmado' THEN
    IF v_estado_cobro = 'Anulado' THEN
      RAISE EXCEPTION 'El cobro % esta anulado y no admite pagos', NEW.id_cobro
        USING ERRCODE = 'check_violation';
    END IF;
    SELECT COALESCE(SUM(monto), 0) INTO v_total FROM detalle_cobro WHERE id_cobro = NEW.id_cobro;
    SELECT COALESCE(SUM(monto), 0) INTO v_pagado
      FROM pago WHERE id_cobro = NEW.id_cobro AND estado = 'Confirmado';
    IF v_pagado + NEW.monto > v_total THEN
      RAISE EXCEPTION 'El pago (%) excede el saldo pendiente del cobro % (total=%, ya pagado=%)',
        NEW.monto, NEW.id_cobro, v_total, v_pagado USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_validar_pago_no_excede_total ON pago;
CREATE TRIGGER trg_validar_pago_no_excede_total BEFORE INSERT OR UPDATE ON pago
  FOR EACH ROW EXECUTE FUNCTION fn_validar_pago_no_excede_total();

-- Los cargos solo se tocan mientras el cobro esta Abierto y nunca por debajo de lo pagado.
CREATE OR REPLACE FUNCTION fn_validar_detalle_cobro() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_id_cobro INT := COALESCE(NEW.id_cobro, OLD.id_cobro);
  v_estado_cobro TEXT;
  v_total  NUMERIC(10,2);
  v_pagado NUMERIC(10,2);
  v_nuevo  NUMERIC(10,2) := 0;
  v_activa BOOLEAN;
BEGIN
  SELECT estado INTO v_estado_cobro FROM cobro WHERE id_cobro = v_id_cobro FOR UPDATE;
  IF v_estado_cobro <> 'Abierto' THEN
    RAISE EXCEPTION 'El cobro % esta % y no admite cambios en sus cargos', v_id_cobro,
      v_estado_cobro USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP <> 'DELETE' THEN
    IF TG_OP = 'INSERT' OR NEW.id_tarifa <> OLD.id_tarifa THEN
      SELECT activa INTO v_activa FROM tarifa WHERE id_tarifa = NEW.id_tarifa;
      IF NOT COALESCE(v_activa, FALSE) THEN
        RAISE EXCEPTION 'La tarifa % no esta activa', NEW.id_tarifa
          USING ERRCODE = 'check_violation';
      END IF;
    END IF;
    v_nuevo := NEW.cantidad * NEW.precio_unitario_aplicado;
  END IF;
  IF TG_OP <> 'INSERT' THEN
    SELECT COALESCE(SUM(monto), 0) INTO v_total FROM detalle_cobro WHERE id_cobro = v_id_cobro;
    SELECT COALESCE(SUM(monto), 0) INTO v_pagado
      FROM pago WHERE id_cobro = v_id_cobro AND estado = 'Confirmado';
    IF v_total - OLD.monto + v_nuevo < v_pagado THEN
      RAISE EXCEPTION 'El total del cobro % no puede ser menor a lo ya pagado (%)',
        v_id_cobro, v_pagado USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN COALESCE(NEW, OLD);
END $$;
DROP TRIGGER IF EXISTS trg_validar_detalle_cobro ON detalle_cobro;
CREATE TRIGGER trg_validar_detalle_cobro BEFORE INSERT OR UPDATE OR DELETE ON detalle_cobro
  FOR EACH ROW EXECUTE FUNCTION fn_validar_detalle_cobro();

-- Estados del cobro: Pagado solo si esta saldado; Anulado solo sin pagos confirmados;
-- Pagado y Anulado son finales.
CREATE OR REPLACE FUNCTION fn_validar_estado_cobro() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_total  NUMERIC(10,2);
  v_pagado NUMERIC(10,2);
BEGIN
  IF NEW.estado = OLD.estado THEN
    RETURN NEW;
  END IF;
  IF OLD.estado IN ('Pagado', 'Anulado') THEN
    RAISE EXCEPTION 'Un cobro % ya no cambia de estado', OLD.estado
      USING ERRCODE = 'check_violation';
  END IF;
  SELECT COALESCE(SUM(monto), 0) INTO v_total FROM detalle_cobro WHERE id_cobro = NEW.id_cobro;
  SELECT COALESCE(SUM(monto), 0) INTO v_pagado
    FROM pago WHERE id_cobro = NEW.id_cobro AND estado = 'Confirmado';
  IF NEW.estado = 'Pagado' AND (v_total = 0 OR v_pagado <> v_total) THEN
    RAISE EXCEPTION 'El cobro % solo pasa a Pagado cuando esta saldado (total=%, pagado=%)',
      NEW.id_cobro, v_total, v_pagado USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.estado = 'Anulado' AND v_pagado > 0 THEN
    RAISE EXCEPTION 'El cobro % tiene pagos confirmados: anula primero los pagos', NEW.id_cobro
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_validar_estado_cobro ON cobro;
CREATE TRIGGER trg_validar_estado_cobro BEFORE UPDATE OF estado ON cobro
  FOR EACH ROW EXECUTE FUNCTION fn_validar_estado_cobro();

-- ---------------------------------------------------------------------------
-- CAMAS E INGRESOS
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ex_ingreso_cama_sin_solape') THEN
    -- Un ingreso sin alta sigue abierto (hasta 'infinity').
    ALTER TABLE ingreso ADD CONSTRAINT ex_ingreso_cama_sin_solape EXCLUDE USING gist (
      id_cama WITH =,
      tsrange(fecha_hora_ingreso, COALESCE(fecha_hora_alta, 'infinity'::timestamp)) WITH &&
    );
  END IF;
END $$;

CREATE OR REPLACE FUNCTION fn_ingreso_un_paciente_una_cama() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_paciente INT;
BEGIN
  SELECT id_paciente INTO v_paciente FROM atencion WHERE id_atencion = NEW.id_atencion;
  -- Serializa los ingresos del mismo paciente (no hay fila comun que bloquear).
  PERFORM pg_advisory_xact_lock(hashtext('ingreso_paciente'), v_paciente);
  IF EXISTS (
    SELECT 1 FROM ingreso i JOIN atencion a ON a.id_atencion = i.id_atencion
    WHERE a.id_paciente = v_paciente AND i.id_atencion <> NEW.id_atencion
      AND tsrange(i.fecha_hora_ingreso, COALESCE(i.fecha_hora_alta, 'infinity'::timestamp))
          && tsrange(NEW.fecha_hora_ingreso, COALESCE(NEW.fecha_hora_alta, 'infinity'::timestamp))
  ) THEN
    RAISE EXCEPTION 'El paciente ya tiene un ingreso en ese periodo'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_ingreso_un_paciente_una_cama ON ingreso;
CREATE TRIGGER trg_ingreso_un_paciente_una_cama BEFORE INSERT OR UPDATE ON ingreso
  FOR EACH ROW EXECUTE FUNCTION fn_ingreso_un_paciente_una_cama();

-- ---------------------------------------------------------------------------
-- ATENCION <-> CITA
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_atencion_cita_coherente() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_paciente INT;
  v_estado TEXT;
BEGIN
  IF NEW.id_cita IS NULL THEN
    RETURN NEW;
  END IF;
  SELECT id_paciente, estado INTO v_paciente, v_estado FROM cita
    WHERE id_cita = NEW.id_cita FOR SHARE;
  IF v_paciente <> NEW.id_paciente THEN
    RAISE EXCEPTION 'La cita % pertenece a otro paciente', NEW.id_cita
      USING ERRCODE = 'check_violation';
  END IF;
  IF v_estado = 'Cancelada' THEN
    RAISE EXCEPTION 'La cita % esta cancelada', NEW.id_cita USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_atencion_cita_coherente ON atencion;
CREATE TRIGGER trg_atencion_cita_coherente BEFORE INSERT OR UPDATE OF id_cita, id_paciente ON atencion
  FOR EACH ROW EXECUTE FUNCTION fn_atencion_cita_coherente();

COMMIT;
