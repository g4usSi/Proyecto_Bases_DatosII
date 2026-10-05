-- MySQL 8.4+, InnoDB. Version revisada del modelo de tu companero.
-- Inicializacion de una BD VACIA; no es una migracion del archivo original.
-- No borra datos ni desactiva las llaves foraneas. Ver docs/revision_mysql.md.
CREATE DATABASE IF NOT EXISTS hospital_pediatrico
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE hospital_pediatrico;
SET time_zone = '+00:00';

CREATE TABLE alergias_conocidas (
  id_alergias INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(150) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE religion (
  id_religion INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;

-- Estado operativo extensible; el archivo del expediente es independiente.
CREATE TABLE estado (
  id_estado INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;
INSERT INTO estado(nombre) VALUES ('Activo'), ('En seguimiento'), ('Referido');

CREATE TABLE tutor (
  id_tutor INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL,
  apellido VARCHAR(100) NOT NULL,
  dpi_pasaporte VARCHAR(30) NULL UNIQUE,
  telefono VARCHAR(30),
  correo_electronico VARCHAR(254), -- Familias pueden compartir correo.
  direccion VARCHAR(300),
  id_religion_fk INT,
  CONSTRAINT fk_tutor_religion FOREIGN KEY(id_religion_fk) REFERENCES religion(id_religion)
) ENGINE=InnoDB;

CREATE TABLE paciente (
  id_paciente INT AUTO_INCREMENT PRIMARY KEY,
  numero_expediente VARCHAR(40) NOT NULL UNIQUE,
  nombre VARCHAR(100) NOT NULL,
  apellido VARCHAR(100) NOT NULL,
  fecha_nacimiento DATE NOT NULL,
  genero VARCHAR(50) NULL, -- No limitar a una sola letra; tampoco inferir sexo clinico.
  sexo_registrado VARCHAR(50) NULL,
  tipo_sangre VARCHAR(5) NULL,
  id_estado_fk INT NOT NULL,
  alergias_evaluadas BOOLEAN NOT NULL DEFAULT FALSE,
  archivado BOOLEAN NOT NULL DEFAULT FALSE,
  fecha_baja DATETIME(6),
  motivo_baja VARCHAR(500),
  creado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  actualizado_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_paciente_estado FOREIGN KEY(id_estado_fk) REFERENCES estado(id_estado),
  CONSTRAINT ck_paciente_archivo CHECK (
    (archivado = FALSE AND fecha_baja IS NULL AND motivo_baja IS NULL) OR
    (archivado = TRUE AND fecha_baja IS NOT NULL
      AND motivo_baja IS NOT NULL AND CHAR_LENGTH(TRIM(motivo_baja)) > 0)),
  CONSTRAINT ck_paciente_sangre CHECK (
    tipo_sangre IS NULL OR tipo_sangre IN ('A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-')),
  INDEX ix_paciente_nombre(apellido, nombre),
  INDEX ix_paciente_estado(archivado, id_estado_fk, id_paciente)
) ENGINE=InnoDB;

-- Parentesco depende del par paciente/tutor; se permiten varios responsables.
CREATE TABLE paciente_tutor (
  id_paciente INT NOT NULL,
  id_tutor INT NOT NULL,
  parentesco VARCHAR(80) NOT NULL,
  es_principal BOOLEAN NOT NULL DEFAULT FALSE,
  autorizado BOOLEAN NOT NULL DEFAULT TRUE,
  paciente_principal INT GENERATED ALWAYS AS
    (CASE WHEN es_principal THEN id_paciente ELSE NULL END) STORED,
  PRIMARY KEY(id_paciente, id_tutor),
  UNIQUE uq_tutor_principal(paciente_principal),
  CONSTRAINT fk_pt_paciente FOREIGN KEY(id_paciente) REFERENCES paciente(id_paciente),
  CONSTRAINT fk_pt_tutor FOREIGN KEY(id_tutor) REFERENCES tutor(id_tutor),
  CONSTRAINT ck_tutor_principal CHECK (NOT es_principal OR autorizado)
) ENGINE=InnoDB;

CREATE TABLE paciente_alergia (
  id_paciente INT NOT NULL,
  id_alergias INT NOT NULL,
  reaccion VARCHAR(500),
  severidad VARCHAR(50),
  observaciones TEXT,
  registrada_en DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY(id_paciente, id_alergias),
  CONSTRAINT fk_pa_paciente FOREIGN KEY(id_paciente) REFERENCES paciente(id_paciente),
  CONSTRAINT fk_pa_alergia FOREIGN KEY(id_alergias) REFERENCES alergias_conocidas(id_alergias)
) ENGINE=InnoDB;

CREATE TABLE medico (
  id_medico INT AUTO_INCREMENT PRIMARY KEY,
  id_profesional_central CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NULL UNIQUE,
  nombre VARCHAR(100) NOT NULL,
  apellido VARCHAR(100) NOT NULL,
  colegiado VARCHAR(50) NOT NULL UNIQUE,
  telefono VARCHAR(30),
  salario DECIMAL(12,2) NULL, -- Restringido; no necesario para atender.
  activo BOOLEAN NOT NULL DEFAULT TRUE,
  CONSTRAINT ck_medico_salario CHECK (salario IS NULL OR salario >= 0)
) ENGINE=InnoDB;

CREATE TABLE medico_especialidad (
  id_especialidad INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB;
CREATE TABLE medico_especialidades (
  id_medico INT NOT NULL,
  id_especialidad INT NOT NULL,
  PRIMARY KEY(id_medico, id_especialidad),
  CONSTRAINT fk_me_medico FOREIGN KEY(id_medico) REFERENCES medico(id_medico),
  CONSTRAINT fk_me_especialidad FOREIGN KEY(id_especialidad)
    REFERENCES medico_especialidad(id_especialidad)
) ENGINE=InnoDB;

CREATE TABLE control_crecimiento (
  id_control INT AUTO_INCREMENT PRIMARY KEY,
  id_paciente_fk INT NOT NULL,
  fecha_registro DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  edad_meses INT NULL, -- Edad observada en esa fecha, no edad actual almacenada.
  peso_kg DECIMAL(6,3) NULL,
  talla_cm DECIMAL(6,2) NULL,
  perimetro_cefalico DECIMAL(5,2) NULL,
  percentil_peso DECIMAL(5,2) NULL,
  percentil_talla DECIMAL(5,2) NULL,
  referencia_percentiles VARCHAR(150),
  observaciones TEXT,
  UNIQUE uq_control_paciente(id_control, id_paciente_fk),
  CONSTRAINT fk_control_paciente FOREIGN KEY(id_paciente_fk) REFERENCES paciente(id_paciente),
  CONSTRAINT ck_control_medidas CHECK (
    (edad_meses IS NULL OR edad_meses >= 0) AND (peso_kg IS NULL OR peso_kg > 0)
    AND (talla_cm IS NULL OR talla_cm > 0)
    AND (perimetro_cefalico IS NULL OR perimetro_cefalico > 0)
    AND (percentil_peso IS NULL OR percentil_peso BETWEEN 0 AND 100)
    AND (percentil_talla IS NULL OR percentil_talla BETWEEN 0 AND 100)),
  INDEX ix_control_historial(id_paciente_fk, fecha_registro, id_control)
) ENGINE=InnoDB;

CREATE TABLE consulta_medica (
  id_consulta INT AUTO_INCREMENT PRIMARY KEY,
  id_paciente INT NOT NULL,
  id_medico INT NOT NULL,
  id_control INT NULL UNIQUE,
  fecha_hora DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  motivo_consulta TEXT NOT NULL,
  diagnostico TEXT NULL, -- Impresion general; los diagnósticos detallados van en tabla hija.
  notas_medicas TEXT,
  CONSTRAINT fk_consulta_paciente FOREIGN KEY(id_paciente) REFERENCES paciente(id_paciente),
  CONSTRAINT fk_consulta_medico FOREIGN KEY(id_medico) REFERENCES medico(id_medico),
  -- Impide asignar a una consulta el control de OTRO paciente, incluso si se edita.
  CONSTRAINT fk_consulta_control FOREIGN KEY(id_control, id_paciente)
    REFERENCES control_crecimiento(id_control, id_paciente_fk),
  CONSTRAINT ck_consulta_motivo CHECK (CHAR_LENGTH(TRIM(motivo_consulta)) > 0),
  INDEX ix_consulta_historial(id_paciente, fecha_hora, id_consulta),
  INDEX ix_consulta_medico(id_medico, fecha_hora)
) ENGINE=InnoDB;

CREATE TABLE consulta_diagnostico (
  id_diagnostico INT AUTO_INCREMENT PRIMARY KEY,
  id_consulta INT NOT NULL,
  codigo VARCHAR(40),
  sistema_codigo VARCHAR(50), -- CIE-10 u otro, sin imponer uno.
  descripcion TEXT NOT NULL,
  es_principal BOOLEAN NOT NULL DEFAULT FALSE,
  CONSTRAINT fk_diag_consulta FOREIGN KEY(id_consulta) REFERENCES consulta_medica(id_consulta)
) ENGINE=InnoDB;
CREATE TABLE consulta_tratamiento (
  id_tratamiento INT AUTO_INCREMENT PRIMARY KEY,
  id_consulta INT NOT NULL,
  descripcion TEXT NOT NULL,
  fecha_inicio DATE,
  fecha_fin DATE,
  CONSTRAINT fk_trat_consulta FOREIGN KEY(id_consulta) REFERENCES consulta_medica(id_consulta),
  CONSTRAINT ck_trat_fechas CHECK (
    fecha_fin IS NULL OR (fecha_inicio IS NOT NULL AND fecha_fin >= fecha_inicio))
) ENGINE=InnoDB;
CREATE TABLE recetas_medicamento (
  id_receta INT AUTO_INCREMENT PRIMARY KEY,
  id_consulta INT NOT NULL,
  medicamento VARCHAR(200) NOT NULL,
  dosis VARCHAR(150) NOT NULL,
  frecuencia VARCHAR(100) NOT NULL,
  duracion_dias INT NULL,
  via_administracion VARCHAR(80),
  instrucciones_adicionales TEXT,
  fecha_emitida DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_receta_consulta FOREIGN KEY(id_consulta) REFERENCES consulta_medica(id_consulta),
  CONSTRAINT ck_receta_duracion CHECK (duracion_dias IS NULL OR duracion_dias > 0)
) ENGINE=InnoDB;

CREATE TABLE nombre_vacuna (
  id_nombre_vacuna INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(150) NOT NULL UNIQUE,
  enfermedades_que_previene TEXT,
  edad_recomendada_meses INT NULL,
  dosis_sugerida VARCHAR(100),
  CONSTRAINT ck_vacuna_edad CHECK (
    edad_recomendada_meses IS NULL OR edad_recomendada_meses >= 0)
) ENGINE=InnoDB;
-- Se conserva el nombre del dueño; representa LOTES, no tipos de vacuna.
CREATE TABLE catalogo_vacunas (
  id_vacuna INT AUTO_INCREMENT PRIMARY KEY,
  nombre_vacuna_fk INT NOT NULL,
  lote_vacuna VARCHAR(80) NOT NULL,
  fabricante VARCHAR(150),
  fecha_ingreso DATE NOT NULL DEFAULT (CURRENT_DATE),
  fecha_vencimiento DATE NOT NULL,
  cantidad INT NOT NULL DEFAULT 0,
  precio_unitario DECIMAL(12,2) NULL,
  UNIQUE uq_vacuna_lote(nombre_vacuna_fk, lote_vacuna),
  UNIQUE uq_lote_tipo(id_vacuna, nombre_vacuna_fk),
  CONSTRAINT fk_lote_vacuna FOREIGN KEY(nombre_vacuna_fk) REFERENCES nombre_vacuna(id_nombre_vacuna),
  CONSTRAINT ck_lote_valores CHECK (
    cantidad >= 0 AND (precio_unitario IS NULL OR precio_unitario >= 0)
    AND (fecha_vencimiento IS NULL OR fecha_vencimiento >= fecha_ingreso)),
  INDEX ix_lote_vencimiento(fecha_vencimiento)
) ENGINE=InnoDB;
CREATE TABLE esquema_vacunacion (
  id_esquema INT AUTO_INCREMENT PRIMARY KEY,
  id_paciente_fk INT NOT NULL,
  id_nombre_vacuna_fk INT NOT NULL,
  id_vacuna_fk INT NULL, -- Se conoce el lote al aplicar, no al programar.
  numero_dosis INT NULL,
  fecha_programada DATE NULL,
  fecha_aplicacion DATETIME(6) NULL,
  estado_aplicacion VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
  id_medico_aplicador INT NULL,
  observaciones_reaccion TEXT,
  CONSTRAINT fk_esquema_paciente FOREIGN KEY(id_paciente_fk) REFERENCES paciente(id_paciente),
  CONSTRAINT fk_esquema_tipo FOREIGN KEY(id_nombre_vacuna_fk) REFERENCES nombre_vacuna(id_nombre_vacuna),
  CONSTRAINT fk_esquema_lote FOREIGN KEY(id_vacuna_fk, id_nombre_vacuna_fk)
    REFERENCES catalogo_vacunas(id_vacuna, nombre_vacuna_fk),
  CONSTRAINT fk_esquema_medico FOREIGN KEY(id_medico_aplicador) REFERENCES medico(id_medico),
  CONSTRAINT ck_esquema_estado CHECK (estado_aplicacion IN ('Pendiente','Aplicada','Cancelada')),
  CONSTRAINT ck_esquema_dosis CHECK (numero_dosis IS NULL OR numero_dosis > 0),
  CONSTRAINT ck_esquema_aplicacion CHECK (
    (estado_aplicacion = 'Aplicada' AND fecha_aplicacion IS NOT NULL
      AND id_vacuna_fk IS NOT NULL AND id_medico_aplicador IS NOT NULL)
    OR (estado_aplicacion <> 'Aplicada' AND fecha_aplicacion IS NULL AND id_vacuna_fk IS NULL)),
  INDEX ix_esquema_paciente(id_paciente_fk, fecha_programada, id_esquema)
) ENGINE=InnoDB;

-- Facturacion del diagrama: opcional para el enunciado, incluida como modulo simple.
CREATE TABLE tipo_de_pago (
  id_tipo_pago INT AUTO_INCREMENT PRIMARY KEY,
  nombre VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB;
INSERT INTO tipo_de_pago(nombre) VALUES ('Efectivo'), ('Tarjeta'), ('Transferencia');
CREATE TABLE facturacion (
  id_facturacion INT AUTO_INCREMENT PRIMARY KEY,
  id_consulta_fk INT NOT NULL,
  fecha_emision DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  descripcion TEXT,
  -- Acumulados mantenidos exclusivamente por triggers; serializan cobros concurrentes.
  total_facturado DECIMAL(14,2) NOT NULL DEFAULT 0,
  total_pagado DECIMAL(14,2) NOT NULL DEFAULT 0,
  CONSTRAINT ck_fact_saldo CHECK (
    total_facturado >= 0 AND total_pagado >= 0 AND total_pagado <= total_facturado),
  CONSTRAINT fk_fact_consulta FOREIGN KEY(id_consulta_fk) REFERENCES consulta_medica(id_consulta)
) ENGINE=InnoDB;
CREATE TABLE detalle_facturacion (
  id_detalle INT AUTO_INCREMENT PRIMARY KEY,
  id_facturacion INT NOT NULL,
  concepto VARCHAR(200) NOT NULL,
  cantidad DECIMAL(10,2) NOT NULL,
  precio_unitario DECIMAL(12,2) NOT NULL,
  monto DECIMAL(14,2) GENERATED ALWAYS AS (ROUND(cantidad * precio_unitario, 2)) STORED,
  CONSTRAINT fk_det_fact FOREIGN KEY(id_facturacion) REFERENCES facturacion(id_facturacion),
  CONSTRAINT ck_det_fact CHECK (cantidad > 0 AND precio_unitario >= 0)
) ENGINE=InnoDB;
CREATE TABLE pago (
  id_pago INT AUTO_INCREMENT PRIMARY KEY,
  id_facturacion INT NOT NULL,
  id_tipo_pago INT NOT NULL,
  monto DECIMAL(14,2) NOT NULL,
  fecha_pago DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  referencia VARCHAR(150), -- Referencia, nunca datos de tarjeta.
  CONSTRAINT fk_pago_fact FOREIGN KEY(id_facturacion) REFERENCES facturacion(id_facturacion),
  CONSTRAINT fk_pago_tipo FOREIGN KEY(id_tipo_pago) REFERENCES tipo_de_pago(id_tipo_pago),
  CONSTRAINT ck_pago_monto CHECK (monto > 0)
) ENGINE=InnoDB;
CREATE VIEW resumen_facturacion AS
SELECT f.id_facturacion, f.id_consulta_fk,
  f.total_facturado AS total, f.total_pagado AS pagado,
  f.total_facturado - f.total_pagado AS saldo
FROM facturacion f;
