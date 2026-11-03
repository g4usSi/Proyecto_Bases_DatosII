-- Cuentas de la entrega academica. Contrasena inicial de las cinco: DemoSalud2026!
-- Requiere 015. Se comparte entre initdb, el ejecutor de migraciones y la API.
-- No modifica cuentas existentes, sus permisos, bloqueos ni contrasenas.
BEGIN;
SELECT pg_advisory_xact_lock(170017);

WITH nuevas AS (
  INSERT INTO identidad.profesional
    (id_profesional, correo, nombres, apellidos, password_hash, establecimiento,
     rol, debe_cambiar_contrasena)
  SELECT gen_random_uuid(), demo.correo, demo.nombres, 'Demo',
    '$argon2id$v=19$m=65536,t=3,p=4$d+Il7+2eQdpU+N5OIWa9nw$/6CSfGaa+57mvcNh0IX1Oa6Uj9V4ZxPt9zlPFd7GRs0',
    demo.establecimiento, demo.rol, FALSE
  FROM (VALUES
    ('superadmin@demo.local', 'Superadmin', NULL::text, 'superusuario'),
    ('admin.hospital@demo.local', 'Admin Hospital', 'hospital_general', 'administrador'),
    ('admin.pediatria@demo.local', 'Admin Pediatria', 'centro_pediatrico', 'administrador'),
    ('admin.laboratorio@demo.local', 'Admin Laboratorio', 'laboratorio_clinico', 'administrador'),
    ('admin.odontologia@demo.local', 'Admin Odontologia', 'clinica_odontologica', 'administrador')
  ) AS demo(correo, nombres, establecimiento, rol)
  WHERE NOT EXISTS (
    SELECT 1 FROM identidad.profesional p
    WHERE p.rol = demo.rol
      AND p.establecimiento IS NOT DISTINCT FROM demo.establecimiento
      AND p.eliminado_en IS NULL
  )
  ON CONFLICT DO NOTHING
  RETURNING id_profesional, rol
)
INSERT INTO identidad.profesional_permiso (id_profesional, permiso)
SELECT n.id_profesional, permiso
FROM nuevas n
CROSS JOIN LATERAL unnest(CASE WHEN n.rol = 'superusuario'
  THEN ARRAY['plataforma:administrar', 'pagos:ver']
  ELSE ARRAY['profesionales:administrar'] END) AS permiso;
COMMIT;
