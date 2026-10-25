-- Administracion de profesionales desde la API (alta, permisos, estado, contrasenas).
--   * Rol 'administrador': una cuenta por institucion que solo gestiona al personal de
--     SU institucion. Tiene un unico permiso, profesionales:administrar, y ningun
--     permiso clinico. La base lo impone aunque se salte la API.
--   * Area (departamento) del profesional: solo existe en el Hospital General.
--   * Bitacora de administracion: solo se agrega; nunca se edita ni se borra.
--   * Permisos minimos para que la API haga estas operaciones y vincule el perfil local
--     (personal_medico) de un profesional nuevo del hospital.
-- Aditivo e idempotente: no borra datos y se puede aplicar mas de una vez.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\postgresql\012_administracion_profesionales.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
BEGIN;
SET LOCAL client_min_messages = warning;

-- ---------------------------------------------------------------------------
-- 1. Rol administrador y permiso profesionales:administrar
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  restriccion TEXT;
BEGIN
  FOR restriccion IN
    SELECT conname FROM pg_constraint
    WHERE conrelid = 'identidad.profesional'::regclass AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%odontologo%'
  LOOP
    EXECUTE format('ALTER TABLE identidad.profesional DROP CONSTRAINT %I', restriccion);
  END LOOP;
END $$;
ALTER TABLE identidad.profesional ADD CONSTRAINT ck_profesional_rol CHECK
  (rol IN ('medico','enfermeria','laboratorista','odontologo','secretaria','administrador'));

INSERT INTO identidad.permiso(codigo) VALUES ('profesionales:administrar') ON CONFLICT DO NOTHING;

-- El administrador tiene SOLO profesionales:administrar, y nadie mas lo tiene.
CREATE OR REPLACE FUNCTION identidad.validar_permiso_administrador() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_rol TEXT;
BEGIN
  SELECT rol INTO v_rol FROM identidad.profesional WHERE id_profesional = NEW.id_profesional;
  IF NEW.permiso = 'profesionales:administrar' AND v_rol <> 'administrador' THEN
    RAISE EXCEPTION 'Solo el rol administrador puede tener profesionales:administrar'
      USING ERRCODE = 'check_violation';
  END IF;
  IF v_rol = 'administrador' AND NEW.permiso <> 'profesionales:administrar' THEN
    RAISE EXCEPTION 'El administrador no puede tener el permiso %', NEW.permiso
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tg_permiso_administrador ON identidad.profesional_permiso;
CREATE TRIGGER tg_permiso_administrador BEFORE INSERT OR UPDATE ON identidad.profesional_permiso
  FOR EACH ROW EXECUTE FUNCTION identidad.validar_permiso_administrador();

CREATE OR REPLACE FUNCTION identidad.validar_cambio_de_rol_administrador() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.rol = 'administrador') <> (OLD.rol = 'administrador') AND EXISTS (
    SELECT 1 FROM identidad.profesional_permiso WHERE id_profesional = NEW.id_profesional
  ) THEN
    RAISE EXCEPTION 'Quita primero los permisos antes de cambiar desde o hacia el rol administrador'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tg_cambio_rol_administrador ON identidad.profesional;
CREATE TRIGGER tg_cambio_rol_administrador BEFORE UPDATE OF rol ON identidad.profesional
  FOR EACH ROW EXECUTE FUNCTION identidad.validar_cambio_de_rol_administrador();

-- ---------------------------------------------------------------------------
-- 2. Datos nuevos de la cuenta
-- ---------------------------------------------------------------------------
ALTER TABLE identidad.profesional
  ADD COLUMN IF NOT EXISTS id_departamento INT REFERENCES public.departamento(id_departamento),
  ADD COLUMN IF NOT EXISTS debe_cambiar_contrasena BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS actualizado_en TIMESTAMPTZ;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_departamento_solo_hospital') THEN
    ALTER TABLE identidad.profesional ADD CONSTRAINT ck_departamento_solo_hospital
      CHECK (id_departamento IS NULL OR establecimiento = 'hospital_general');
  END IF;
END $$;
COMMENT ON COLUMN identidad.profesional.id_departamento IS
  'Area del profesional (solo Hospital General)';
COMMENT ON COLUMN identidad.profesional.debe_cambiar_contrasena IS
  'TRUE tras un alta o restablecimiento: la persona debe elegir su propia contrasena';
COMMENT ON COLUMN identidad.profesional.bloqueado_hasta IS
  'Bloqueo por intentos fallidos (temporal) o por administracion (9999-12-31)';

-- ---------------------------------------------------------------------------
-- 3. Bitacora de administracion (solo agregar)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS identidad.bitacora_profesionales (
  id_evento BIGSERIAL PRIMARY KEY,
  ocurrido_en TIMESTAMPTZ NOT NULL DEFAULT now(),
  id_actor UUID NOT NULL,
  id_profesional UUID NOT NULL REFERENCES identidad.profesional(id_profesional),
  establecimiento TEXT NOT NULL REFERENCES identidad.establecimiento(codigo),
  accion TEXT NOT NULL CHECK (accion IN
    ('alta', 'cambio', 'restablecer_contrasena', 'cambiar_contrasena')),
  -- Que cambio (permisos, estado, area). Nunca contrasenas ni hashes.
  detalle JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS ix_bitacora_profesional
  ON identidad.bitacora_profesionales(id_profesional, ocurrido_en);
COMMENT ON TABLE identidad.bitacora_profesionales IS
  'Restringido: altas, cambios de permisos/estado y restablecimientos de contrasena';

CREATE OR REPLACE FUNCTION identidad.bitacora_solo_agregar() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'La bitacora de administracion no se modifica ni se borra'
    USING ERRCODE = 'check_violation';
END $$;
DROP TRIGGER IF EXISTS tg_bitacora_solo_agregar ON identidad.bitacora_profesionales;
CREATE TRIGGER tg_bitacora_solo_agregar BEFORE UPDATE OR DELETE
  ON identidad.bitacora_profesionales
  FOR EACH ROW EXECUTE FUNCTION identidad.bitacora_solo_agregar();

-- ---------------------------------------------------------------------------
-- 4. Permisos minimos de la cuenta de la API
-- ---------------------------------------------------------------------------
GRANT INSERT ON identidad.profesional TO historiales_app;
GRANT UPDATE (nombres, apellidos, password_hash, activo, id_departamento,
              debe_cambiar_contrasena, actualizado_en)
  ON identidad.profesional TO historiales_app;
-- Retirar un permiso es borrar su fila; no hay datos clinicos en esta tabla.
GRANT INSERT, DELETE ON identidad.profesional_permiso TO historiales_app;
GRANT SELECT, INSERT ON identidad.bitacora_profesionales TO historiales_app;
GRANT USAGE ON SEQUENCE identidad.bitacora_profesionales_id_evento_seq TO historiales_app;
-- Selector de area y validacion del departamento.
GRANT SELECT ON public.departamento TO historiales_app;
-- Perfil local en el hospital de un profesional dado de alta por la API.
GRANT INSERT (nombres, apellidos, rol, estado, id_profesional_central)
  ON public.personal_medico TO historiales_app;
GRANT UPDATE (nombres, apellidos, rol, estado) ON public.personal_medico TO historiales_app;
GRANT USAGE ON SEQUENCE public.personal_medico_id_personal_seq TO historiales_app;

COMMIT;
