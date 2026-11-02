-- Administracion general sobre las cuentas institucionales. Aditiva e idempotente.
BEGIN;
ALTER TABLE identidad.profesional
  ALTER COLUMN establecimiento DROP NOT NULL,
  ADD COLUMN IF NOT EXISTS eliminado_en TIMESTAMPTZ;
ALTER TABLE identidad.profesional DROP CONSTRAINT IF EXISTS ck_profesional_rol;
ALTER TABLE identidad.profesional ADD CONSTRAINT ck_profesional_rol CHECK
  (rol IN ('medico','enfermeria','laboratorista','odontologo','secretaria',
           'administrador','superusuario'));
ALTER TABLE identidad.profesional DROP CONSTRAINT IF EXISTS ck_cuenta_plataforma;
ALTER TABLE identidad.profesional ADD CONSTRAINT ck_cuenta_plataforma CHECK
  ((rol = 'superusuario') = (establecimiento IS NULL));
ALTER TABLE identidad.profesional DROP CONSTRAINT IF EXISTS ck_cuenta_eliminada;
ALTER TABLE identidad.profesional ADD CONSTRAINT ck_cuenta_eliminada CHECK
  (eliminado_en IS NULL OR NOT activo);
-- CHECK con NULL no basta para impedir un area en una cuenta de plataforma.
ALTER TABLE identidad.profesional DROP CONSTRAINT IF EXISTS ck_departamento_solo_hospital;
ALTER TABLE identidad.profesional ADD CONSTRAINT ck_departamento_solo_hospital CHECK
  (id_departamento IS NULL OR establecimiento IS NOT DISTINCT FROM 'hospital_general');

CREATE UNIQUE INDEX IF NOT EXISTS ux_un_superusuario
  ON identidad.profesional ((rol)) WHERE rol = 'superusuario' AND eliminado_en IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_un_admin_por_entidad
  ON identidad.profesional (establecimiento)
  WHERE rol = 'administrador' AND activo AND eliminado_en IS NULL;
INSERT INTO identidad.permiso(codigo) VALUES ('plataforma:administrar') ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION identidad.validar_permiso_administrador() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE v_rol TEXT;
BEGIN
  SELECT rol INTO v_rol FROM identidad.profesional WHERE id_profesional = NEW.id_profesional;
  IF (NEW.permiso = 'profesionales:administrar' AND v_rol <> 'administrador')
     OR (NEW.permiso = 'plataforma:administrar' AND v_rol <> 'superusuario')
     OR (v_rol = 'administrador' AND NEW.permiso <> 'profesionales:administrar')
     OR (v_rol = 'superusuario' AND NEW.permiso NOT IN ('plataforma:administrar','pagos:ver'))
  THEN
    RAISE EXCEPTION 'Permiso incompatible con el nivel de administracion'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION identidad.validar_cambio_de_rol_administrador() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.rol <> OLD.rol
     AND (NEW.rol IN ('administrador','superusuario') OR OLD.rol IN ('administrador','superusuario'))
     AND EXISTS (SELECT 1 FROM identidad.profesional_permiso WHERE id_profesional = NEW.id_profesional)
  THEN
    RAISE EXCEPTION 'Quita primero los permisos antes de cambiar el nivel de administracion'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION identidad.validar_reactivacion() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.eliminado_en IS NOT NULL AND
     (NEW.activo OR NEW.eliminado_en IS DISTINCT FROM OLD.eliminado_en) THEN
    RAISE EXCEPTION 'Una cuenta eliminada no se puede rehabilitar'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.establecimiento IS DISTINCT FROM OLD.establecimiento THEN
    RAISE EXCEPTION 'Una cuenta no cambia de institucion'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS tg_no_reactivar ON identidad.profesional;
CREATE TRIGGER tg_no_reactivar BEFORE UPDATE ON identidad.profesional
  FOR EACH ROW EXECUTE FUNCTION identidad.validar_reactivacion();

ALTER TABLE identidad.bitacora_profesionales
  DROP CONSTRAINT IF EXISTS bitacora_profesionales_accion_check;
ALTER TABLE identidad.bitacora_profesionales ADD CONSTRAINT bitacora_profesionales_accion_check
  CHECK (accion IN ('alta','cambio','restablecer_contrasena','cambiar_contrasena','eliminar'));
-- El superusuario tambien puede cambiar SU contrasena. Ese evento no tiene entidad.
ALTER TABLE identidad.bitacora_profesionales ALTER COLUMN establecimiento DROP NOT NULL;
CREATE INDEX IF NOT EXISTS ix_bitacora_institucion_evento
  ON identidad.bitacora_profesionales (establecimiento, id_evento DESC);
GRANT UPDATE (eliminado_en) ON identidad.profesional TO historiales_app;
COMMIT;
