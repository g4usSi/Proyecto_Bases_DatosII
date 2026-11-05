-- DEMOSTRACION: estructura minima del Hospital General para probar la aplicacion en local.
-- Areas, habitaciones, camas, servicios y tarifas. La API solo lee estas tablas; el hospital
-- real debe cargar su propia estructura y precios.
--
-- Uso (con PostgreSQL de compose iniciado):
--   docker compose cp database/ejemplos/hospital_demo.sql postgres:/tmp/hospital_demo.sql
--   docker compose exec postgres psql -U historiales_admin -d hospital_general -f /tmp/hospital_demo.sql
--
-- Es idempotente: si ya hay areas cargadas no hace nada.

BEGIN;

DO $$
DECLARE
  dep_emergencias INT;
  dep_medicina    INT;
  dep_pediatria   INT;
  srv_dia_general INT;
  srv_dia_emerg   INT;
  hab             INT;
BEGIN
  IF EXISTS (SELECT 1 FROM departamento) THEN
    RAISE NOTICE 'El hospital ya tiene areas: no se cargan datos de demostracion.';
    RETURN;
  END IF;

  -- Servicios cobrables con su tarifa general vigente.
  INSERT INTO servicio (nombre, tipo, unidad_cobro) VALUES ('Día de estancia en emergencias', 'Hospitalizacion', 'Por_dia') RETURNING id_servicio INTO srv_dia_emerg;
  INSERT INTO servicio (nombre, tipo, unidad_cobro) VALUES ('Día de habitación general', 'Hospitalizacion', 'Por_dia') RETURNING id_servicio INTO srv_dia_general;
  INSERT INTO tarifa (id_servicio, monto_vigente) VALUES (srv_dia_emerg, 850.00), (srv_dia_general, 600.00);

  WITH s AS (
    INSERT INTO servicio (nombre, tipo, unidad_cobro) VALUES
      ('Consulta de medicina general', 'Consulta', 'Por_evento'),
      ('Consulta de especialidad', 'Consulta', 'Por_evento'),
      ('Curación simple', 'Procedimiento', 'Por_evento'),
      ('Electrocardiograma', 'Examen', 'Por_evento'),
      ('Radiografía de tórax', 'Examen', 'Por_evento')
    RETURNING id_servicio, nombre
  )
  INSERT INTO tarifa (id_servicio, monto_vigente)
  SELECT id_servicio, CASE nombre
    WHEN 'Consulta de medicina general' THEN 200.00
    WHEN 'Consulta de especialidad' THEN 350.00
    WHEN 'Curación simple' THEN 150.00
    WHEN 'Electrocardiograma' THEN 275.00
    ELSE 300.00 END
  FROM s;

  INSERT INTO departamento (descripcion) VALUES ('Emergencias') RETURNING id_departamento INTO dep_emergencias;
  INSERT INTO departamento (descripcion) VALUES ('Medicina interna') RETURNING id_departamento INTO dep_medicina;
  INSERT INTO departamento (descripcion) VALUES ('Pediatría') RETURNING id_departamento INTO dep_pediatria;

  -- Emergencias: dos boxes de cuatro camas.
  FOR i IN 1..2 LOOP
    INSERT INTO habitacion (id_departamento, numero) VALUES (dep_emergencias, 'E' || i) RETURNING id_habitacion INTO hab;
    INSERT INTO cama (id_habitacion, id_servicio_estancia, codigo, estado_operativo)
    SELECT hab, srv_dia_emerg, 'E-' || lpad(((i - 1) * 4 + n)::text, 2, '0'), 'Disponible' FROM generate_series(1, 4) n;
  END LOOP;

  -- Medicina interna: tres habitaciones de dos camas.
  FOR i IN 1..3 LOOP
    INSERT INTO habitacion (id_departamento, numero) VALUES (dep_medicina, (200 + i)::text) RETURNING id_habitacion INTO hab;
    INSERT INTO cama (id_habitacion, id_servicio_estancia, codigo, estado_operativo)
    SELECT hab, srv_dia_general, (200 + i) || '-' || chr(64 + n), 'Disponible' FROM generate_series(1, 2) n;
  END LOOP;

  -- Pediatria: dos habitaciones de dos camas; una en mantenimiento para ver ese estado.
  FOR i IN 1..2 LOOP
    INSERT INTO habitacion (id_departamento, numero) VALUES (dep_pediatria, (300 + i)::text) RETURNING id_habitacion INTO hab;
    INSERT INTO cama (id_habitacion, id_servicio_estancia, codigo, estado_operativo)
    SELECT hab, srv_dia_general, (300 + i) || '-' || chr(64 + n), 'Disponible' FROM generate_series(1, 2) n;
  END LOOP;
  UPDATE cama SET estado_operativo = 'Mantenimiento' WHERE codigo = '302-B';
END $$;

COMMIT;
