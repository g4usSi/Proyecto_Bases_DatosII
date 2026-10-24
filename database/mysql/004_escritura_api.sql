-- Escrituras de la API en el Centro Pediatrico (registrar paciente, consultas con
-- diagnosticos/tratamientos/recetas, archivar) y busqueda por nombre.
-- Aditivo e idempotente: no borra ni cambia datos, se puede aplicar mas de una vez.
-- Aplicar a mano en una base existente (PowerShell, desde la raiz); despues aplicar tambien 005:
--   Get-Content database\mysql\004_escritura_api.sql | docker compose exec -T mysql mysql -uroot -p"$env:MYSQL_ROOT_PASSWORD" hospital_pediatrico
USE hospital_pediatrico;
DELIMITER $$

-- MySQL no tiene ADD COLUMN IF NOT EXISTS: este ayudante lo emula y se elimina al final.
DROP PROCEDURE IF EXISTS agregar_columna$$
CREATE PROCEDURE agregar_columna(IN tabla VARCHAR(64), IN columna VARCHAR(64), IN definicion TEXT)
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = tabla AND COLUMN_NAME = columna
  ) THEN
    SET @ddl = CONCAT('ALTER TABLE `', tabla, '` ADD COLUMN `', columna, '` ', definicion);
    PREPARE sentencia FROM @ddl;
    EXECUTE sentencia;
    DEALLOCATE PREPARE sentencia;
  END IF;
END$$
DELIMITER ;

-- 1. Paciente: contacto opcional, detalle de la baja y quien la dio (identidad central).
CALL agregar_columna('paciente', 'telefono', 'VARCHAR(30) NULL');
CALL agregar_columna('paciente', 'correo_electronico', 'VARCHAR(254) NULL');
CALL agregar_columna('paciente', 'direccion', 'VARCHAR(300) NULL');
CALL agregar_columna('paciente', 'detalle_baja', 'VARCHAR(500) NULL');
CALL agregar_columna('paciente', 'archivado_por',
  'CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT ''Restringido: identidad central''');
-- Mismo largo que acepta la API (120).
ALTER TABLE paciente
  MODIFY nombre VARCHAR(120) NOT NULL,
  MODIFY apellido VARCHAR(120) NOT NULL;

-- 2. Recetas: largos que acepta la API.
ALTER TABLE recetas_medicamento
  MODIFY dosis VARCHAR(200) NOT NULL,
  MODIFY frecuencia VARCHAR(200) NOT NULL,
  MODIFY via_administracion VARCHAR(100) NULL;

-- 3. Medicos: el codigo de colegiado real lo completa el hospital; mientras tanto la
--    sincronizacion de cuentas usa un valor provisional unico (PEND-<uuid>).

DROP PROCEDURE agregar_columna;
