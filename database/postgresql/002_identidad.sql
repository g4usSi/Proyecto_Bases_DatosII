-- Directorio transversal. Una cuenta -> un establecimiento, nunca una cuenta de paciente.
-- Aplicable junto al esquema clinico; las tablas clinicas siguen en public.
BEGIN;
CREATE SCHEMA IF NOT EXISTS identidad;
CREATE TABLE IF NOT EXISTS identidad.establecimiento (
  codigo TEXT PRIMARY KEY CHECK (codigo IN
    ('hospital_general','centro_pediatrico','laboratorio_clinico','clinica_odontologica')),
  nombre TEXT NOT NULL,
  motor TEXT NOT NULL,
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK ((codigo = 'hospital_general' AND motor = 'postgresql')
    OR (codigo = 'centro_pediatrico' AND motor = 'mysql')
    OR (codigo = 'laboratorio_clinico' AND motor = 'mongodb')
    OR (codigo = 'clinica_odontologica' AND motor = 'firestore'))
);
INSERT INTO identidad.establecimiento(codigo, nombre, motor) VALUES
 ('hospital_general','Hospital General','postgresql'),
 ('centro_pediatrico','Centro Pediatrico','mysql'),
 ('laboratorio_clinico','Laboratorio Clinico','mongodb'),
 ('clinica_odontologica','Clinica Odontologica','firestore')
ON CONFLICT(codigo) DO NOTHING;

CREATE TABLE IF NOT EXISTS identidad.profesional (
  id_profesional UUID PRIMARY KEY,
  correo TEXT NOT NULL UNIQUE CHECK (correo = lower(btrim(correo))),
  nombres TEXT NOT NULL CHECK (length(btrim(nombres)) > 0),
  apellidos TEXT NOT NULL CHECK (length(btrim(apellidos)) > 0),
  password_hash TEXT NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
  establecimiento TEXT NOT NULL REFERENCES identidad.establecimiento(codigo),
  rol TEXT NOT NULL CHECK (rol IN ('medico','enfermeria','laboratorista','odontologo')),
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  version_token INTEGER NOT NULL DEFAULT 0 CHECK (version_token >= 0),
  creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_profesional_establecimiento
 ON identidad.profesional(establecimiento);
CREATE TABLE IF NOT EXISTS identidad.permiso (
  codigo TEXT PRIMARY KEY
);
INSERT INTO identidad.permiso(codigo) VALUES
 ('pacientes:leer'), ('pacientes:registrar'), ('historiales:leer'),
 ('consultas:registrar'), ('historiales:archivar') ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS identidad.profesional_permiso (
  id_profesional UUID NOT NULL REFERENCES identidad.profesional(id_profesional) ON DELETE CASCADE,
  permiso TEXT NOT NULL REFERENCES identidad.permiso(codigo),
  PRIMARY KEY(id_profesional, permiso)
);
COMMENT ON COLUMN identidad.profesional.password_hash IS 'Restringido: hash Argon2id; nunca devolver en API';
COMMENT ON COLUMN identidad.profesional.correo IS 'Confidencial: identidad de acceso';
COMMENT ON COLUMN identidad.profesional.version_token IS 'Incrementar para invalidar todas las sesiones';
COMMIT;
