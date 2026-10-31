-- Administracion en dos niveles (docs/administracion_general.md):
--   * Superusuario de plataforma: UNA cuenta sin establecimiento ni permisos clinicos.
--     Crea cuentas en cualquier entidad (incluido su administrador), es el unico que
--     elimina y ve pagos en solo lectura (plataforma:administrar + pagos:ver).
--   * Administrador de cada entidad: el mismo de 012, ahora uno ACTIVO por entidad.
--   * Baja definitiva logica: eliminado_en. La fila se conserva porque la referencian el
--     historial clinico y la bitacora; el correo sigue reservado (UNIQUE) y la cuenta no
--     puede volver a habilitarse, ni siquiera con SQL directo.
-- Aditivo e idempotente: no borra datos y se puede aplicar mas de una vez.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\postgresql\015_administracion_dos_niveles.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
BEGIN;
SET LOCAL client_min_messages = warning;

-- ---------------------------------------------------------------------------
-- 1. Rol superusuario sin establecimiento
-- ---------------------------------------------------------------------------
ALTER TABLE identidad.profesional ALTER COLUMN establecimiento DROP NOT NULL;

ALTER TABLE identidad.profesional DROP CONSTRAINT IF EXISTS ck_profesional_rol;
ALTER TABLE identidad.profesional ADD CONSTRAINT ck_profesional_rol CHECK (rol IN
  ('medico','enfermeria','laboratorista','odontologo','secretaria','administrador',
   'superusuario'));

-- Sin establecimiento <=> superusuario. El area (ck_departamento_solo_hospital) tambien
-- queda nula, porque exige establecimiento = 'hospital_general'.
ALTER TABLE identidad.profesional DROP CONSTRAINT IF EXISTS ck_superusuario_sin_establecimiento;
ALTER TABLE identidad.profesional ADD CONSTRAINT ck_superusuario_sin_establecimiento
  CHECK ((rol = 'superusuario') = (establecimiento IS NULL));

-- ---------------------------------------------------------------------------
-- 2. Baja definitiva logica
-- ---------------------------------------------------------------------------
ALTER TABLE identidad.profesional ADD COLUMN IF NOT EXISTS eliminado_en TIMESTAMPTZ;
ALTER TABLE identidad.profesional DROP CONSTRAINT IF EXISTS ck_eliminada_inactiva;
ALTER TABLE identidad.profesional ADD CONSTRAINT ck_eliminada_inactiva
  CHECK (eliminado_en IS NULL OR NOT activo);
COMMENT ON COLUMN identidad.profesional.eliminado_en IS
  'Baja definitiva (solo el superusuario). No se revierte; el correo sigue reservado';

-- Una cuenta eliminada no vuelve: ni activo = TRUE ni quitar o mover la fecha de baja.
CREATE OR REPLACE FUNCTION identidad.validar_reactivacion() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.eliminado_en IS NOT NULL AND (
    NEW.activo OR NEW.eliminado_en IS DISTINCT FROM OLD.eliminado_en
  ) THEN
    RAISE EXCEPTION 'Una cuenta eliminada no se puede volver a habilitar'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tg_validar_reactivacion ON identidad.profesional;
CREATE TRIGGER tg_validar_reactivacion BEFORE UPDATE ON identidad.profesional
  FOR EACH ROW EXECUTE FUNCTION identidad.validar_reactivacion();

-- ---------------------------------------------------------------------------
-- 3. Unicidad: un superusuario y un administrador activo por entidad
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF (SELECT count(*) FROM identidad.profesional
      WHERE rol = 'superusuario' AND eliminado_en IS NULL) > 1 THEN
    RAISE EXCEPTION 'Hay mas de un superusuario: deja uno antes de aplicar 015';
  END IF;
  IF EXISTS (SELECT establecimiento FROM identidad.profesional
             WHERE rol = 'administrador' AND activo AND eliminado_en IS NULL
             GROUP BY establecimiento HAVING count(*) > 1) THEN
    RAISE EXCEPTION 'Hay entidades con mas de un administrador activo: desactiva los sobrantes antes de aplicar 015';
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS ux_un_superusuario ON identidad.profesional ((rol))
  WHERE rol = 'superusuario' AND eliminado_en IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_un_admin_por_entidad ON identidad.profesional (establecimiento)
  WHERE rol = 'administrador' AND activo AND eliminado_en IS NULL;

-- ---------------------------------------------------------------------------
-- 4. Permisos de cada nivel
-- ---------------------------------------------------------------------------
INSERT INTO identidad.permiso(codigo) VALUES ('plataforma:administrar') ON CONFLICT DO NOTHING;

-- administrador: solo profesionales:administrar (como en 012).
-- superusuario: solo plataforma:administrar y pagos:ver (pagos en solo lectura).
-- Nadie mas puede tener profesionales:administrar ni plataforma:administrar.
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
  IF NEW.permiso = 'plataforma:administrar' AND v_rol <> 'superusuario' THEN
    RAISE EXCEPTION 'Solo el superusuario puede tener plataforma:administrar'
      USING ERRCODE = 'check_violation';
  END IF;
  IF v_rol = 'administrador' AND NEW.permiso <> 'profesionales:administrar' THEN
    RAISE EXCEPTION 'El administrador no puede tener el permiso %', NEW.permiso
      USING ERRCODE = 'check_violation';
  END IF;
  IF v_rol = 'superusuario' AND NEW.permiso NOT IN ('plataforma:administrar', 'pagos:ver') THEN
    RAISE EXCEPTION 'El superusuario no puede tener el permiso %', NEW.permiso
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

-- Cambiar desde o hacia administrador o superusuario exige quitar antes los permisos.
CREATE OR REPLACE FUNCTION identidad.validar_cambio_de_rol_administrador() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.rol IS DISTINCT FROM OLD.rol
     AND (NEW.rol IN ('administrador', 'superusuario')
          OR OLD.rol IN ('administrador', 'superusuario'))
     AND EXISTS (SELECT 1 FROM identidad.profesional_permiso
                 WHERE id_profesional = NEW.id_profesional) THEN
    RAISE EXCEPTION 'Quita primero los permisos antes de cambiar desde o hacia un rol de administracion'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------------------
-- 5. Bitacora: accion 'eliminar'
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  restriccion TEXT;
BEGIN
  FOR restriccion IN
    SELECT conname FROM pg_constraint
    WHERE conrelid = 'identidad.bitacora_profesionales'::regclass AND contype = 'c'
      AND pg_get_constraintdef(oid) LIKE '%restablecer_contrasena%'
  LOOP
    EXECUTE format('ALTER TABLE identidad.bitacora_profesionales DROP CONSTRAINT %I', restriccion);
  END LOOP;
END $$;
ALTER TABLE identidad.bitacora_profesionales ADD CONSTRAINT ck_bitacora_accion CHECK (accion IN
  ('alta', 'cambio', 'restablecer_contrasena', 'cambiar_contrasena', 'eliminar'));
-- Es la entidad de la cuenta afectada. Solo queda nula cuando el superusuario cambia su
-- propia contrasena (no pertenece a ninguna entidad); esas entradas solo las ve el.
ALTER TABLE identidad.bitacora_profesionales ALTER COLUMN establecimiento DROP NOT NULL;
CREATE INDEX IF NOT EXISTS ix_bitacora_establecimiento
  ON identidad.bitacora_profesionales(establecimiento, ocurrido_en DESC);

-- ---------------------------------------------------------------------------
-- 6. Permisos minimos de la cuenta de la API
-- ---------------------------------------------------------------------------
GRANT UPDATE (eliminado_en) ON identidad.profesional TO historiales_app;

COMMIT;
