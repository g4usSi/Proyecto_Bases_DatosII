-- Rol secretaria (clinica odontologica: registro de pacientes y agenda de citas)
-- y permisos de citas. Idempotente: se puede aplicar a un volumen ya inicializado.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\postgresql\006_rol_secretaria_citas.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
BEGIN;

-- 1. Reemplazar el CHECK de roles (su nombre lo genera PostgreSQL; se busca por contenido).
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
  (rol IN ('medico','enfermeria','laboratorista','odontologo','secretaria'));

-- 2. Permisos de agenda.
INSERT INTO identidad.permiso(codigo) VALUES ('citas:leer'), ('citas:gestionar')
ON CONFLICT DO NOTHING;

-- 3. Una secretaria nunca puede tener acceso clinico (diagnosticos, consultas, recetas).
--    Se valida en la base para que ninguna herramienta lo salte.
CREATE OR REPLACE FUNCTION identidad.permisos_clinicos() RETURNS TEXT[]
LANGUAGE sql IMMUTABLE AS $$ SELECT ARRAY['historiales:leer','consultas:registrar'] $$;

CREATE OR REPLACE FUNCTION identidad.validar_permiso_por_rol() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.permiso = ANY (identidad.permisos_clinicos()) AND EXISTS (
    SELECT 1 FROM identidad.profesional
    WHERE id_profesional = NEW.id_profesional AND rol = 'secretaria'
  ) THEN
    RAISE EXCEPTION 'El rol secretaria no puede tener el permiso clinico %', NEW.permiso
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION identidad.validar_cambio_a_secretaria() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.rol = 'secretaria' AND EXISTS (
    SELECT 1 FROM identidad.profesional_permiso
    WHERE id_profesional = NEW.id_profesional AND permiso = ANY (identidad.permisos_clinicos())
  ) THEN
    RAISE EXCEPTION 'Quita primero los permisos clinicos antes de asignar el rol secretaria'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS tg_permiso_por_rol ON identidad.profesional_permiso;
CREATE TRIGGER tg_permiso_por_rol BEFORE INSERT OR UPDATE ON identidad.profesional_permiso
  FOR EACH ROW EXECUTE FUNCTION identidad.validar_permiso_por_rol();

DROP TRIGGER IF EXISTS tg_cambio_a_secretaria ON identidad.profesional;
CREATE TRIGGER tg_cambio_a_secretaria BEFORE UPDATE OF rol ON identidad.profesional
  FOR EACH ROW EXECUTE FUNCTION identidad.validar_cambio_a_secretaria();

COMMIT;
