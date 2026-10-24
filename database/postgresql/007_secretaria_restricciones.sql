-- Decisiones del equipo sobre el rol secretaria (se suman a 006):
--   * existe solo en la clinica odontologica;
--   * no accede a informacion clinica (historiales:leer, consultas:registrar);
--   * tampoco puede dar de baja un historial (historiales:archivar).
-- Idempotente: se puede aplicar a un volumen ya inicializado.
-- Aplicar a mano (PowerShell, desde la raiz del proyecto):
--   Get-Content database\postgresql\007_secretaria_restricciones.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
BEGIN;

-- 1. Permisos vedados para la secretaria (reemplaza el uso de permisos_clinicos()).
CREATE OR REPLACE FUNCTION identidad.permisos_vedados_secretaria() RETURNS TEXT[]
LANGUAGE sql IMMUTABLE AS $$
  SELECT ARRAY['historiales:leer','consultas:registrar','historiales:archivar']
$$;

CREATE OR REPLACE FUNCTION identidad.validar_permiso_por_rol() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.permiso = ANY (identidad.permisos_vedados_secretaria()) AND EXISTS (
    SELECT 1 FROM identidad.profesional
    WHERE id_profesional = NEW.id_profesional AND rol = 'secretaria'
  ) THEN
    RAISE EXCEPTION 'El rol secretaria no puede tener el permiso %', NEW.permiso
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION identidad.validar_cambio_a_secretaria() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.rol = 'secretaria' AND EXISTS (
    SELECT 1 FROM identidad.profesional_permiso
    WHERE id_profesional = NEW.id_profesional
      AND permiso = ANY (identidad.permisos_vedados_secretaria())
  ) THEN
    RAISE EXCEPTION 'Quita primero los permisos clinicos y de archivo antes de asignar el rol secretaria'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;

-- Si alguna secretaria creada antes de esta regla tenia permiso de archivar, se le quita.
DELETE FROM identidad.profesional_permiso pp
USING identidad.profesional p
WHERE pp.id_profesional = p.id_profesional
  AND p.rol = 'secretaria'
  AND pp.permiso = 'historiales:archivar';

-- 2. La secretaria solo existe en la clinica odontologica.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_secretaria_solo_odontologia'
             AND conrelid = 'identidad.profesional'::regclass) THEN
    ALTER TABLE identidad.profesional DROP CONSTRAINT ck_secretaria_solo_odontologia;
  END IF;
END $$;
ALTER TABLE identidad.profesional ADD CONSTRAINT ck_secretaria_solo_odontologia
  CHECK (rol <> 'secretaria' OR establecimiento = 'clinica_odontologica');

COMMIT;
