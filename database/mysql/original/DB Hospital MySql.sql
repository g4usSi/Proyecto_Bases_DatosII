-- MySQL Workbench Forward Engineering

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- -----------------------------------------------------
-- Schema mydb
-- -----------------------------------------------------
-- -----------------------------------------------------
-- Schema hospital_pediatrico
-- -----------------------------------------------------

-- -----------------------------------------------------
-- Schema hospital_pediatrico
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `hospital_pediatrico` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci ;
USE `hospital_pediatrico` ;

-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`alergias_conocidas`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`alergias_conocidas` (
  `id_alergias` INT NOT NULL AUTO_INCREMENT,
  `nombre` VARCHAR(100) NOT NULL,
  PRIMARY KEY (`id_alergias`),
  UNIQUE INDEX `nombre` (`nombre` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`nombre_vacuna`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`nombre_vacuna` (
  `id_nombre_vacuna` INT NOT NULL AUTO_INCREMENT,
  `nombre` VARCHAR(150) NOT NULL,
  `enfermedades_que_previene` TEXT NULL DEFAULT NULL,
  PRIMARY KEY (`id_nombre_vacuna`),
  UNIQUE INDEX `nombre` (`nombre` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`catalogo_vacunas`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`catalogo_vacunas` (
  `id_vacuna` INT NOT NULL AUTO_INCREMENT,
  `nombre_vacuna_fk` INT NOT NULL,
  `edad_recomendada_meses` INT NOT NULL,
  `dosis_sugerida` VARCHAR(50) NOT NULL,
  `lote_vacuna` VARCHAR(50) NOT NULL,
  `fecha_ingreso` DATE NOT NULL DEFAULT curdate(),
  `cantidad` INT NOT NULL DEFAULT '0',
  `precio_unitario` DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (`id_vacuna`),
  UNIQUE INDEX `lote_vacuna` (`lote_vacuna` ASC) VISIBLE,
  INDEX `nombre_vacuna_fk` (`nombre_vacuna_fk` ASC) VISIBLE,
  CONSTRAINT `catalogo_vacunas_ibfk_1`
    FOREIGN KEY (`nombre_vacuna_fk`)
    REFERENCES `hospital_pediatrico`.`nombre_vacuna` (`id_nombre_vacuna`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`religion`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`religion` (
  `id_religion` INT NOT NULL AUTO_INCREMENT,
  `nombre` VARCHAR(100) NOT NULL,
  PRIMARY KEY (`id_religion`),
  UNIQUE INDEX `nombre` (`nombre` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`tutor`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`tutor` (
  `id_tutor` INT NOT NULL AUTO_INCREMENT,
  `nombre` VARCHAR(100) NOT NULL,
  `apellido` VARCHAR(100) NOT NULL,
  `dpi_pasaporte` VARCHAR(20) NOT NULL,
  `parentesco` VARCHAR(50) NOT NULL,
  `telefono` VARCHAR(20) NULL DEFAULT NULL,
  `correo_electronico` VARCHAR(150) NULL DEFAULT NULL,
  `direccion` VARCHAR(200) NULL DEFAULT NULL,
  `id_religion_fk` INT NULL DEFAULT NULL,
  PRIMARY KEY (`id_tutor`),
  UNIQUE INDEX `dpi_pasaporte` (`dpi_pasaporte` ASC) VISIBLE,
  UNIQUE INDEX `correo_electronico` (`correo_electronico` ASC) VISIBLE,
  INDEX `id_religion_fk` (`id_religion_fk` ASC) VISIBLE,
  CONSTRAINT `tutor_ibfk_1`
    FOREIGN KEY (`id_religion_fk`)
    REFERENCES `hospital_pediatrico`.`religion` (`id_religion`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`estado`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`estado` (
  `id_estado` INT NOT NULL AUTO_INCREMENT,
  `nombre` VARCHAR(50) NOT NULL,
  PRIMARY KEY (`id_estado`),
  UNIQUE INDEX `nombre` (`nombre` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`paciente`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`paciente` (
  `id_paciente` INT NOT NULL AUTO_INCREMENT,
  `id_tutor_fk` INT NOT NULL,
  `nombre` VARCHAR(100) NOT NULL,
  `apellido` VARCHAR(100) NOT NULL,
  `fecha_nacimiento` DATE NOT NULL,
  `genero` CHAR(1) NOT NULL,
  `tipo_sangre` VARCHAR(5) NULL DEFAULT NULL,
  `id_alergia_fk` INT NULL DEFAULT NULL,
  `id_estado_fk` INT NOT NULL,
  PRIMARY KEY (`id_paciente`),
  INDEX `id_tutor_fk` (`id_tutor_fk` ASC) VISIBLE,
  INDEX `id_alergia_fk` (`id_alergia_fk` ASC) VISIBLE,
  INDEX `id_estado_fk` (`id_estado_fk` ASC) VISIBLE,
  CONSTRAINT `paciente_ibfk_1`
    FOREIGN KEY (`id_tutor_fk`)
    REFERENCES `hospital_pediatrico`.`tutor` (`id_tutor`),
  CONSTRAINT `paciente_ibfk_2`
    FOREIGN KEY (`id_alergia_fk`)
    REFERENCES `hospital_pediatrico`.`alergias_conocidas` (`id_alergias`),
  CONSTRAINT `paciente_ibfk_3`
    FOREIGN KEY (`id_estado_fk`)
    REFERENCES `hospital_pediatrico`.`estado` (`id_estado`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`medico`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`medico` (
  `id_medico` INT NOT NULL AUTO_INCREMENT,
  `nombre` VARCHAR(100) NOT NULL,
  `apellido` VARCHAR(100) NOT NULL,
  `colegiado` VARCHAR(30) NOT NULL,
  `telefono` VARCHAR(20) NULL DEFAULT NULL,
  `salario` DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (`id_medico`),
  UNIQUE INDEX `colegiado` (`colegiado` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`control_crecimiento`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`control_crecimiento` (
  `id_control` INT NOT NULL AUTO_INCREMENT,
  `id_paciente_fk` INT NOT NULL,
  `fecha_registro` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `edad_meses` INT NOT NULL,
  `peso_kg` DECIMAL(5,2) NOT NULL,
  `talla_cm` DECIMAL(5,2) NOT NULL,
  `perimetro_cefalico` DECIMAL(5,2) NULL DEFAULT NULL,
  `percentil_peso` DECIMAL(5,2) NULL DEFAULT NULL,
  `percentil_talla` DECIMAL(5,2) NULL DEFAULT NULL,
  `observaciones` TEXT NULL DEFAULT NULL,
  PRIMARY KEY (`id_control`),
  INDEX `id_paciente_fk` (`id_paciente_fk` ASC) VISIBLE,
  CONSTRAINT `control_crecimiento_ibfk_1`
    FOREIGN KEY (`id_paciente_fk`)
    REFERENCES `hospital_pediatrico`.`paciente` (`id_paciente`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`consulta_medica`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`consulta_medica` (
  `id_consulta` INT NOT NULL AUTO_INCREMENT,
  `id_paciente` INT NOT NULL,
  `id_medico` INT NOT NULL,
  `id_control` INT NULL DEFAULT NULL,
  `fecha_hora` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `motivo_consulta` TEXT NOT NULL,
  `diagnostico` TEXT NULL DEFAULT NULL,
  `notas_medicas` TEXT NULL DEFAULT NULL,
  PRIMARY KEY (`id_consulta`),
  UNIQUE INDEX `id_control` (`id_control` ASC) VISIBLE,
  INDEX `id_paciente` (`id_paciente` ASC) VISIBLE,
  INDEX `id_medico` (`id_medico` ASC) VISIBLE,
  CONSTRAINT `consulta_medica_ibfk_1`
    FOREIGN KEY (`id_paciente`)
    REFERENCES `hospital_pediatrico`.`paciente` (`id_paciente`),
  CONSTRAINT `consulta_medica_ibfk_2`
    FOREIGN KEY (`id_medico`)
    REFERENCES `hospital_pediatrico`.`medico` (`id_medico`),
  CONSTRAINT `consulta_medica_ibfk_3`
    FOREIGN KEY (`id_control`)
    REFERENCES `hospital_pediatrico`.`control_crecimiento` (`id_control`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`esquema_vacunacion`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`esquema_vacunacion` (
  `id_esquema` INT NOT NULL AUTO_INCREMENT,
  `id_paciente_fk` INT NOT NULL,
  `id_vacuna_fk` INT NOT NULL,
  `fecha_programada` DATE NOT NULL,
  `fecha_aplicacion` DATE NULL DEFAULT NULL,
  `estado_aplicacion` VARCHAR(30) NOT NULL DEFAULT 'Pendiente',
  `observaciones_reaccion` TEXT NULL DEFAULT NULL,
  PRIMARY KEY (`id_esquema`),
  INDEX `id_paciente_fk` (`id_paciente_fk` ASC) VISIBLE,
  INDEX `id_vacuna_fk` (`id_vacuna_fk` ASC) VISIBLE,
  CONSTRAINT `esquema_vacunacion_ibfk_1`
    FOREIGN KEY (`id_paciente_fk`)
    REFERENCES `hospital_pediatrico`.`paciente` (`id_paciente`),
  CONSTRAINT `esquema_vacunacion_ibfk_2`
    FOREIGN KEY (`id_vacuna_fk`)
    REFERENCES `hospital_pediatrico`.`catalogo_vacunas` (`id_vacuna`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`medico_especialidad`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`medico_especialidad` (
  `id_especialidad` INT NOT NULL AUTO_INCREMENT,
  `nombre` VARCHAR(100) NOT NULL,
  PRIMARY KEY (`id_especialidad`),
  UNIQUE INDEX `nombre` (`nombre` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`medico_especialidades`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`medico_especialidades` (
  `id_medico` INT NOT NULL,
  `id_especialidad` INT NOT NULL,
  PRIMARY KEY (`id_medico`, `id_especialidad`),
  INDEX `id_especialidad` (`id_especialidad` ASC) VISIBLE,
  CONSTRAINT `medico_especialidades_ibfk_1`
    FOREIGN KEY (`id_medico`)
    REFERENCES `hospital_pediatrico`.`medico` (`id_medico`)
    ON DELETE CASCADE,
  CONSTRAINT `medico_especialidades_ibfk_2`
    FOREIGN KEY (`id_especialidad`)
    REFERENCES `hospital_pediatrico`.`medico_especialidad` (`id_especialidad`)
    ON DELETE CASCADE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


-- -----------------------------------------------------
-- Table `hospital_pediatrico`.`recetas_medicamento`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `hospital_pediatrico`.`recetas_medicamento` (
  `id_receta` INT NOT NULL AUTO_INCREMENT,
  `id_consulta` INT NOT NULL,
  `medicamento` VARCHAR(150) NOT NULL,
  `dosis` VARCHAR(50) NOT NULL,
  `frecuencia` VARCHAR(50) NOT NULL,
  `duracion_dias` INT NOT NULL,
  `instrucciones_adicionales` TEXT NULL DEFAULT NULL,
  PRIMARY KEY (`id_receta`),
  INDEX `id_consulta` (`id_consulta` ASC) VISIBLE,
  CONSTRAINT `recetas_medicamento_ibfk_1`
    FOREIGN KEY (`id_consulta`)
    REFERENCES `hospital_pediatrico`.`consulta_medica` (`id_consulta`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COLLATE = utf8mb4_0900_ai_ci;


SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;
