-- Hospital General: camas, ingresos (emergencias, programados, traslados), altas y ordenes
-- medicas con descripcion. Las reglas viven en la base aunque se salte la API:
--   * un ingreso solo ocupa una cama Disponible y la deja Ocupada (dos ingresos
--     simultaneos a la misma cama: uno espera al otro y el segundo se rechaza);
--   * una cama Ocupada con un ingreso abierto no cambia de estado a mano, y nadie la
--     marca Ocupada sin un ingreso abierto;
--   * el alta cierra el ingreso una sola vez y deja la cama en Limpieza;
--   * un ingreso no se reasigna a otra cama, paciente o fecha.
-- Aditivo e idempotente. Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\postgresql\013_camas_ingresos.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
BEGIN;
SET LOCAL client_min_messages = warning;

INSERT INTO identidad.permiso(codigo) VALUES ('camas:gestionar') ON CONFLICT DO NOTHING;

-- Ordenes de examen, procedimiento o interconsulta necesitan decir QUE se pide.
ALTER TABLE orden_medica ADD COLUMN IF NOT EXISTS descripcion VARCHAR(500);
COMMENT ON COLUMN orden_medica.descripcion IS 'Confidencial: que se solicita';
ALTER TABLE ingreso ALTER COLUMN motivo_alta TYPE VARCHAR(300);

-- ---------------------------------------------------------------------------
-- 1. Ingreso -> cama
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_ingreso_reservar_cama() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_estado TEXT;
BEGIN
  IF NEW.fecha_hora_alta IS NOT NULL THEN
    RETURN NEW;  -- carga historica: no ocupa la cama hoy
  END IF;
  -- Bloquea la cama: dos ingresos simultaneos a la misma cama se validan de uno en uno.
  SELECT estado_operativo INTO v_estado FROM cama WHERE id_cama = NEW.id_cama FOR UPDATE;
  IF v_estado IS DISTINCT FROM 'Disponible' THEN
    RAISE EXCEPTION 'La cama % no esta disponible (%)', NEW.id_cama, COALESCE(v_estado, 'no existe')
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_ingreso_reservar_cama ON ingreso;
CREATE TRIGGER trg_ingreso_reservar_cama BEFORE INSERT ON ingreso
  FOR EACH ROW EXECUTE FUNCTION fn_ingreso_reservar_cama();

CREATE OR REPLACE FUNCTION fn_ingreso_ocupar_cama() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.fecha_hora_alta IS NULL THEN
    UPDATE cama SET estado_operativo = 'Ocupada' WHERE id_cama = NEW.id_cama;
  END IF;
  RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS trg_ingreso_ocupar_cama ON ingreso;
CREATE TRIGGER trg_ingreso_ocupar_cama AFTER INSERT ON ingreso
  FOR EACH ROW EXECUTE FUNCTION fn_ingreso_ocupar_cama();

-- Un ingreso no se reescribe; el alta se da una sola vez.
CREATE OR REPLACE FUNCTION fn_ingreso_inmutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id_atencion <> OLD.id_atencion OR NEW.id_cama <> OLD.id_cama
     OR NEW.fecha_hora_ingreso <> OLD.fecha_hora_ingreso OR NEW.tipo <> OLD.tipo THEN
    RAISE EXCEPTION 'Un ingreso no se reasigna: da el alta y registra un traslado'
      USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.fecha_hora_alta IS NOT NULL AND (
       NEW.fecha_hora_alta IS DISTINCT FROM OLD.fecha_hora_alta
       OR NEW.motivo_alta IS DISTINCT FROM OLD.motivo_alta) THEN
    RAISE EXCEPTION 'El ingreso ya tiene alta y no cambia' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.fecha_hora_alta IS NOT NULL AND COALESCE(btrim(NEW.motivo_alta), '') = '' THEN
    RAISE EXCEPTION 'El alta necesita un motivo' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_ingreso_inmutable ON ingreso;
CREATE TRIGGER trg_ingreso_inmutable BEFORE UPDATE ON ingreso
  FOR EACH ROW EXECUTE FUNCTION fn_ingreso_inmutable();

CREATE OR REPLACE FUNCTION fn_ingreso_liberar_cama() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.fecha_hora_alta IS NULL AND NEW.fecha_hora_alta IS NOT NULL THEN
    UPDATE cama SET estado_operativo = 'Limpieza'
      WHERE id_cama = NEW.id_cama AND estado_operativo = 'Ocupada';
  END IF;
  RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS trg_ingreso_liberar_cama ON ingreso;
CREATE TRIGGER trg_ingreso_liberar_cama AFTER UPDATE OF fecha_hora_alta ON ingreso
  FOR EACH ROW EXECUTE FUNCTION fn_ingreso_liberar_cama();

-- ---------------------------------------------------------------------------
-- 2. Estado de la cama coherente con sus ingresos
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_cama_estado_coherente() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_abierto BOOLEAN;
BEGIN
  IF NEW.estado_operativo = OLD.estado_operativo THEN
    RETURN NEW;
  END IF;
  SELECT EXISTS (SELECT 1 FROM ingreso WHERE id_cama = NEW.id_cama AND fecha_hora_alta IS NULL)
    INTO v_abierto;
  IF NEW.estado_operativo = 'Ocupada' AND NOT v_abierto THEN
    RAISE EXCEPTION 'Una cama solo queda Ocupada con un ingreso' USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.estado_operativo <> 'Ocupada' AND v_abierto THEN
    RAISE EXCEPTION 'La cama % tiene un paciente ingresado: da el alta primero', NEW.id_cama
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_cama_estado_coherente ON cama;
CREATE TRIGGER trg_cama_estado_coherente BEFORE UPDATE OF estado_operativo ON cama
  FOR EACH ROW EXECUTE FUNCTION fn_cama_estado_coherente();

CREATE INDEX IF NOT EXISTS idx_ingreso_abierto ON ingreso(id_cama) WHERE fecha_hora_alta IS NULL;
CREATE INDEX IF NOT EXISTS idx_ingreso_fecha ON ingreso(fecha_hora_ingreso);

-- ---------------------------------------------------------------------------
-- 3. Permisos minimos de la cuenta de la API (sigue sin DELETE)
-- ---------------------------------------------------------------------------
GRANT SELECT ON departamento, habitacion, cama, ingreso TO historiales_app;
GRANT UPDATE (estado_operativo) ON cama TO historiales_app;
GRANT INSERT ON ingreso TO historiales_app;
GRANT UPDATE (fecha_hora_alta, motivo_alta) ON ingreso TO historiales_app;

COMMIT;
