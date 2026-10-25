-- Hospital General: citas con duracion y sin choques, adendas a consultas (solo agregar),
-- correccion de datos del paciente y permisos minimos de la API para todo ello.
-- Aditivo e idempotente: no borra datos y se puede aplicar mas de una vez.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\postgresql\009_citas_adendas_edicion.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
BEGIN;
SET LOCAL client_min_messages = warning;  -- sin avisos "ya existe, se omite"

CREATE EXTENSION IF NOT EXISTS btree_gist;  -- restriccion de exclusion (citas sin choques)

-- ---------------------------------------------------------------------------
-- 1. CITAS. El modelo original guarda fecha + hora (hora local del hospital) sin
--    duracion, por lo que dos citas no podian detectarse como cruzadas.
-- ---------------------------------------------------------------------------
ALTER TABLE cita
  ADD COLUMN IF NOT EXISTS duracion_minutos INT NOT NULL DEFAULT 30,
  ADD COLUMN IF NOT EXISTS creada_por UUID,
  ADD COLUMN IF NOT EXISTS creada_en TIMESTAMPTZ NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS motivo_cambio VARCHAR(300),
  ADD COLUMN IF NOT EXISTS actualizada_por UUID;
ALTER TABLE cita ALTER COLUMN motivo TYPE VARCHAR(300);
COMMENT ON COLUMN cita.creada_por IS 'Restringido: identidad central de quien agendo';
COMMENT ON COLUMN cita.fecha IS 'Fecha LOCAL del hospital (zona horaria de la API)';
COMMENT ON COLUMN cita.hora IS 'Hora LOCAL del hospital (zona horaria de la API)';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cita_duracion') THEN
    ALTER TABLE cita ADD CONSTRAINT ck_cita_duracion
      CHECK (duracion_minutos BETWEEN 5 AND 480);
  END IF;
  -- Un profesional no puede tener dos citas vigentes que se crucen. La base lo garantiza
  -- aunque dos secretarias reserven el mismo horario a la vez.
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ex_cita_sin_choques') THEN
    ALTER TABLE cita ADD CONSTRAINT ex_cita_sin_choques EXCLUDE USING gist (
      id_personal WITH =,
      tsrange(fecha + hora, fecha + hora + duracion_minutos * interval '1 minute') WITH &&
    ) WHERE (estado IN ('Programada', 'Confirmada'));
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_cita_personal_fecha ON cita(id_personal, fecha);

-- Reglas al crear/cambiar una cita (la base las impone aunque se salte la API).
CREATE OR REPLACE FUNCTION fn_cita_validar() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_estado_paciente TEXT;
  v_estado_personal TEXT;
BEGIN
  IF TG_OP = 'INSERT' THEN
    SELECT estado INTO v_estado_paciente FROM paciente
      WHERE id_paciente = NEW.id_paciente FOR SHARE;
    IF v_estado_paciente = 'Inactivo' THEN
      RAISE EXCEPTION 'El expediente esta archivado' USING ERRCODE = 'check_violation';
    END IF;
    SELECT estado INTO v_estado_personal FROM personal_medico
      WHERE id_personal = NEW.id_personal;
    IF v_estado_personal IS DISTINCT FROM 'Activo' THEN
      RAISE EXCEPTION 'El profesional esta inactivo' USING ERRCODE = 'check_violation';
    END IF;
  ELSE
    IF NEW.id_paciente <> OLD.id_paciente OR NEW.id_personal <> OLD.id_personal
       OR NEW.fecha <> OLD.fecha OR NEW.hora <> OLD.hora
       OR NEW.duracion_minutos <> OLD.duracion_minutos THEN
      RAISE EXCEPTION 'Una cita no se reasigna ni se reprograma: cancela y agenda otra'
        USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.estado IN ('Cancelada', 'Atendida', 'No_asistio') AND NEW.estado <> OLD.estado THEN
      RAISE EXCEPTION 'Una cita % ya no cambia de estado', OLD.estado
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_cita_validar ON cita;
CREATE TRIGGER trg_cita_validar BEFORE INSERT OR UPDATE ON cita
  FOR EACH ROW EXECUTE FUNCTION fn_cita_validar();

-- ---------------------------------------------------------------------------
-- 2. ADENDAS. Agregar diagnosticos/tratamientos/recetas/nota a una consulta ya guardada.
--    La API solo AGREGA. La base lo refuerza: las notas solo crecen por el final y la
--    identidad de la consulta no cambia.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_atencion_inmutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.id_paciente <> OLD.id_paciente OR NEW.id_personal <> OLD.id_personal
     OR NEW.tipo_atencion <> OLD.tipo_atencion OR NEW.fecha_hora <> OLD.fecha_hora
     OR NEW.motivo IS DISTINCT FROM OLD.motivo THEN
    RAISE EXCEPTION 'No se reasigna ni se reescribe una consulta historica'
      USING ERRCODE = 'check_violation';
  END IF;
  IF COALESCE(OLD.notas, '') <> '' AND (
       NEW.notas IS NULL OR left(NEW.notas, length(OLD.notas)) <> OLD.notas) THEN
    RAISE EXCEPTION 'Las notas de una consulta solo admiten adendas al final'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_atencion_inmutable ON atencion;
CREATE TRIGGER trg_atencion_inmutable BEFORE UPDATE ON atencion
  FOR EACH ROW EXECUTE FUNCTION fn_atencion_inmutable();

-- Tampoco se agregan diagnosticos ni ordenes a una consulta de un historial archivado.
CREATE OR REPLACE FUNCTION fn_hija_atencion_paciente_activo() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_estado TEXT;
BEGIN
  SELECT p.estado INTO v_estado
    FROM atencion a JOIN paciente p ON p.id_paciente = a.id_paciente
    WHERE a.id_atencion = NEW.id_atencion FOR SHARE OF p;
  IF v_estado = 'Inactivo' THEN
    RAISE EXCEPTION 'El expediente esta archivado' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_diagnostico_paciente_activo ON diagnostico;
CREATE TRIGGER trg_diagnostico_paciente_activo BEFORE INSERT ON diagnostico
  FOR EACH ROW EXECUTE FUNCTION fn_hija_atencion_paciente_activo();
DROP TRIGGER IF EXISTS trg_orden_paciente_activo ON orden_medica;
CREATE TRIGGER trg_orden_paciente_activo BEFORE INSERT ON orden_medica
  FOR EACH ROW EXECUTE FUNCTION fn_hija_atencion_paciente_activo();

-- ---------------------------------------------------------------------------
-- 3. CORRECCION DE DATOS DEL PACIENTE (nombre, nacimiento, contacto) solo si esta activo.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_paciente_nacimiento_pasado') THEN
    -- NOT VALID: se aplica a datos nuevos sin rechazar historicos ya cargados.
    ALTER TABLE paciente ADD CONSTRAINT ck_paciente_nacimiento_pasado
      CHECK (fecha_nacimiento IS NULL OR fecha_nacimiento <= CURRENT_DATE) NOT VALID;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION fn_paciente_archivado_inmutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.estado = 'Inactivo' AND (
       NEW.nombres IS DISTINCT FROM OLD.nombres OR NEW.apellidos IS DISTINCT FROM OLD.apellidos
       OR NEW.fecha_nacimiento IS DISTINCT FROM OLD.fecha_nacimiento
       OR NEW.telefono IS DISTINCT FROM OLD.telefono
       OR NEW.correo_electronico IS DISTINCT FROM OLD.correo_electronico
       OR NEW.direccion IS DISTINCT FROM OLD.direccion
       OR NEW.alergias_evaluadas IS DISTINCT FROM OLD.alergias_evaluadas) THEN
    RAISE EXCEPTION 'El expediente esta archivado' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_paciente_archivado_inmutable ON paciente;
CREATE TRIGGER trg_paciente_archivado_inmutable BEFORE UPDATE ON paciente
  FOR EACH ROW EXECUTE FUNCTION fn_paciente_archivado_inmutable();

-- ---------------------------------------------------------------------------
-- 4. PERMISOS MINIMOS de la cuenta de la API (sigue sin DELETE en ninguna tabla).
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT ON cita TO historiales_app;
GRANT UPDATE (estado, motivo_cambio, actualizada_por) ON cita TO historiales_app;
GRANT USAGE ON SEQUENCE cita_id_cita_seq TO historiales_app;
GRANT UPDATE (notas) ON atencion TO historiales_app;
GRANT UPDATE (nombres, apellidos, fecha_nacimiento, telefono, correo_electronico, direccion,
              alergias_evaluadas) ON paciente TO historiales_app;
-- La API solo necesita identificar al profesional: nada de colegiado, telefono ni correo.
REVOKE SELECT ON personal_medico FROM historiales_app;
GRANT SELECT (id_personal, nombres, apellidos, rol, estado, id_profesional_central)
  ON personal_medico TO historiales_app;

COMMIT;
