-- Escrituras de la API en el Hospital General (registrar paciente, consultas con
-- diagnosticos/tratamientos/recetas, archivar) y busqueda por nombre.
-- Todo es aditivo: no borra ni cambia datos. Idempotente. La cuenta de la API
-- recibe solo los permisos minimos; NO puede borrar nada.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\postgresql\008_escritura_api.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
BEGIN;
SET LOCAL client_min_messages = warning;  -- sin avisos "ya existe, se omite"

CREATE EXTENSION IF NOT EXISTS unaccent;  -- busqueda sin acentos

-- 1. Paciente: alergias (opcionales), detalle de la baja y contacto con los mismos
--    largos que acepta la API.
ALTER TABLE paciente
  ADD COLUMN IF NOT EXISTS alergias_evaluadas BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS detalle_baja VARCHAR(500),
  ADD COLUMN IF NOT EXISTS archivado_por UUID;
ALTER TABLE paciente
  ALTER COLUMN telefono TYPE VARCHAR(30),
  ALTER COLUMN direccion TYPE VARCHAR(300),
  ALTER COLUMN correo_electronico TYPE VARCHAR(254);
COMMENT ON COLUMN paciente.alergias_evaluadas IS
  'FALSE = no se pregunto por alergias; TRUE con 0 filas = sin alergias conocidas';
COMMENT ON COLUMN paciente.archivado_por IS 'Restringido: identidad central de quien dio la baja';

CREATE TABLE IF NOT EXISTS paciente_alergia (
    id_paciente INT NOT NULL REFERENCES paciente(id_paciente)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
    sustancia   VARCHAR(120) NOT NULL CHECK (length(btrim(sustancia)) > 0),
    reaccion    VARCHAR(300),
    severidad   VARCHAR(50),
    PRIMARY KEY (id_paciente, sustancia)
);
COMMENT ON TABLE paciente_alergia IS 'Restringido: informacion clinica';

-- 2. Atencion (consulta): motivo y notas con el largo que acepta la API.
ALTER TABLE atencion
  ADD COLUMN IF NOT EXISTS motivo VARCHAR(500),
  ADD COLUMN IF NOT EXISTS notas TEXT;

-- 3. Diagnosticos, tratamientos y recetas: codigo CIE-10 opcional y largos de la API.
ALTER TABLE diagnostico
  ADD COLUMN IF NOT EXISTS codigo VARCHAR(20),
  ADD COLUMN IF NOT EXISTS sistema_codigo VARCHAR(20);
ALTER TABLE diagnostico ALTER COLUMN descripcion TYPE VARCHAR(500);
ALTER TABLE tratamiento ALTER COLUMN descripciones TYPE VARCHAR(1000);
ALTER TABLE detalle_receta
  ALTER COLUMN medicamento TYPE VARCHAR(200),
  ALTER COLUMN dosis TYPE VARCHAR(200),
  ALTER COLUMN frecuencia TYPE VARCHAR(200),
  ALTER COLUMN indicaciones TYPE VARCHAR(1000);
ALTER TABLE detalle_receta
  ADD COLUMN IF NOT EXISTS via_administracion VARCHAR(100),
  ADD COLUMN IF NOT EXISTS duracion_dias INT;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_detalle_receta_duracion_dias') THEN
    ALTER TABLE detalle_receta ADD CONSTRAINT ck_detalle_receta_duracion_dias
      CHECK (duracion_dias IS NULL OR duracion_dias > 0);
  END IF;
END $$;

-- 4. Regla en la base: no se registran atenciones en un historial archivado.
--    FOR SHARE hace que una baja concurrente espere a que termine la consulta.
CREATE OR REPLACE FUNCTION fn_atencion_paciente_activo() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_estado TEXT;
BEGIN
  SELECT estado INTO v_estado FROM paciente WHERE id_paciente = NEW.id_paciente FOR SHARE;
  IF v_estado = 'Inactivo' THEN
    RAISE EXCEPTION 'El expediente esta archivado' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_atencion_paciente_activo ON atencion;
CREATE TRIGGER trg_atencion_paciente_activo BEFORE INSERT ON atencion
  FOR EACH ROW EXECUTE FUNCTION fn_atencion_paciente_activo();

-- 5. Permisos minimos de la cuenta de la API (sin DELETE en ninguna tabla).
GRANT SELECT, INSERT ON paciente TO historiales_app;
GRANT UPDATE (estado, fecha_baja, motivo_baja, detalle_baja, archivado_por)
  ON paciente TO historiales_app;
GRANT SELECT, INSERT ON paciente_alergia, atencion, diagnostico, tratamiento,
  orden_medica, receta, detalle_receta TO historiales_app;
GRANT SELECT ON personal_medico TO historiales_app;
GRANT USAGE ON SEQUENCE paciente_id_paciente_seq, atencion_id_atencion_seq,
  diagnostico_id_diagnostico_seq, tratamiento_id_tratamiento_seq,
  orden_medica_id_orden_seq, receta_id_receta_seq, detalle_receta_id_detalle_seq
  TO historiales_app;

COMMIT;
