-- Campos del esquema original usados por la pulsera y el perfil propio del mockup.
BEGIN;
GRANT SELECT ON especialidad, personal_especialidad TO historiales_app;
GRANT SELECT (colegiado, telefono) ON personal_medico TO historiales_app;
GRANT UPDATE (grupo_sanguineo) ON paciente TO historiales_app;
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_grupo_sanguineo_api'
                 AND conrelid = 'paciente'::regclass) THEN
    ALTER TABLE paciente ADD CONSTRAINT ck_grupo_sanguineo_api CHECK
      (grupo_sanguineo IS NULL OR grupo_sanguineo IN ('A+','A-','B+','B-','AB+','AB-','O+','O-'))
      NOT VALID;
  END IF;
END $$;
COMMIT;
