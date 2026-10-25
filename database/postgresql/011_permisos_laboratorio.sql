-- Permisos del modulo de laboratorio (ordenes, resultados y validacion). Idempotente.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\postgresql\011_permisos_laboratorio.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
--   laboratorio:resultados -> tomar muestras y registrar resultados de una orden.
--   laboratorio:validar    -> validar una orden (despues ya no se modifica).
-- Solicitar y cancelar ordenes usa consultas:registrar; consultarlas, historiales:leer o
-- laboratorio:resultados. La secretaria no puede tenerlos (permisos clinicos).
INSERT INTO identidad.permiso(codigo) VALUES ('laboratorio:resultados'), ('laboratorio:validar')
ON CONFLICT DO NOTHING;

-- La secretaria (solo clinica odontologica) tampoco puede tener estos permisos: los dos
-- triggers de 007 consultan esta funcion. Si alguna secretaria ya los tuviera, se retiran.
CREATE OR REPLACE FUNCTION identidad.permisos_vedados_secretaria() RETURNS TEXT[]
LANGUAGE sql IMMUTABLE AS $$
  SELECT ARRAY['historiales:leer','consultas:registrar','historiales:archivar',
               'laboratorio:resultados','laboratorio:validar']
$$;

DELETE FROM identidad.profesional_permiso pp
USING identidad.profesional p
WHERE pp.id_profesional = p.id_profesional AND p.rol = 'secretaria'
  AND pp.permiso IN ('laboratorio:resultados','laboratorio:validar');
