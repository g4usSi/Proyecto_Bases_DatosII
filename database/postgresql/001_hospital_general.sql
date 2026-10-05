-- =====================================================================
-- HOSPITAL GENERAL — Script de creación de base de datos (PostgreSQL)
-- VERSIÓN FINAL CONSOLIDADA
--
-- Incluye:
--   - Modelo base (infraestructura, personas, agenda, atención/ingreso,
--     expediente clínico, órdenes/recetas)
--   - Estado del paciente (desactivación/archivo de historiales)
--   - UNIQUE cita <-> atencion
--   - Encargado (persona responsable del paciente)
--   - Módulo de pagos: Servicio, Tarifa (con historial de precio),
--     Cobro, Detalle_Cobro, Metodo_Pago, Pago
--
-- Correcciones aplicadas sobre el último diagrama recibido:
--   - Pago: eliminadas las columnas duplicadas (fecha_hora x2, estado x2)
--   - Metodo_Pago: eliminada la fila id_metodo_pago repetida/auto-referenciada
--   - Agregado índice único parcial en Tarifa para que no existan dos
--     tarifas "activas" simultáneas para el mismo servicio (+ médico)
-- =====================================================================

BEGIN;

-- =====================================================================
-- INFRAESTRUCTURA
-- =====================================================================

CREATE TABLE departamento (
    id_departamento SERIAL PRIMARY KEY,
    descripcion     VARCHAR(200) NOT NULL
);

CREATE TABLE habitacion (
    id_habitacion   SERIAL PRIMARY KEY,
    id_departamento INT NOT NULL REFERENCES departamento(id_departamento)
                        ON UPDATE CASCADE ON DELETE RESTRICT,
    numero          VARCHAR(10) NOT NULL
);

-- =====================================================================
-- PERSONAS
-- =====================================================================

CREATE TABLE encargado (
    id_encargado SERIAL PRIMARY KEY,
    nombres      VARCHAR(100) NOT NULL,
    apellidos    VARCHAR(100) NOT NULL,
    dpi          VARCHAR(20) UNIQUE,
    telefono     VARCHAR(20)
);

CREATE TABLE paciente (
    id_paciente        SERIAL PRIMARY KEY,
    id_encargado       INT REFERENCES encargado(id_encargado)
                           ON UPDATE CASCADE ON DELETE SET NULL,
    nombres            VARCHAR(100) NOT NULL,
    apellidos          VARCHAR(100) NOT NULL,
    dpi                VARCHAR(20) UNIQUE,
    fecha_nacimiento   DATE,
    grupo_sanguineo    VARCHAR(5),
    genero             VARCHAR(10),
    telefono           VARCHAR(20),
    direccion          VARCHAR(200),
    correo_electronico VARCHAR(100),
    estado             VARCHAR(20) NOT NULL DEFAULT 'Activo'
                           CHECK (estado IN ('Activo', 'Inactivo')),
    fecha_baja         DATE,
    motivo_baja        VARCHAR(100),
    CONSTRAINT chk_paciente_baja_consistente CHECK (
        (estado = 'Activo'   AND fecha_baja IS NULL AND motivo_baja IS NULL)
     OR (estado = 'Inactivo' AND fecha_baja IS NOT NULL AND motivo_baja IS NOT NULL)
    )
);

CREATE TABLE personal_medico (
    id_personal SERIAL PRIMARY KEY,
    nombres     VARCHAR(100) NOT NULL,
    apellidos   VARCHAR(100) NOT NULL,
    rol         VARCHAR(50) NOT NULL
                    CHECK (rol IN ('Medico', 'Enfermero', 'Tecnico', 'Administrativo')),
    colegiado   VARCHAR(50),
    telefono    VARCHAR(20),
    correo      VARCHAR(100),
    estado      VARCHAR(20) NOT NULL DEFAULT 'Activo'
                    CHECK (estado IN ('Activo', 'Inactivo', 'Suspendido'))
);

CREATE TABLE especialidad (
    id_especialidad SERIAL PRIMARY KEY,
    nombre          VARCHAR(100) NOT NULL UNIQUE,
    descripcion     VARCHAR(200)
);

CREATE TABLE personal_especialidad (
    id_personal     INT NOT NULL REFERENCES personal_medico(id_personal)
                        ON UPDATE CASCADE ON DELETE CASCADE,
    id_especialidad INT NOT NULL REFERENCES especialidad(id_especialidad)
                        ON UPDATE CASCADE ON DELETE RESTRICT,
    PRIMARY KEY (id_personal, id_especialidad)
);

-- =====================================================================
-- MÓDULO DE PAGOS — catálogos (van antes de Cama, que ya depende de Servicio)
-- =====================================================================

CREATE TABLE servicio (
    id_servicio  SERIAL PRIMARY KEY,
    nombre       VARCHAR(150) NOT NULL,
    tipo         VARCHAR(20) NOT NULL
                     CHECK (tipo IN ('Consulta', 'Procedimiento', 'Hospitalizacion', 'Examen', 'Otro')),
    unidad_cobro VARCHAR(20) NOT NULL
                     CHECK (unidad_cobro IN ('Por_evento', 'Por_dia', 'Por_sesion')),
    activo       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE tarifa (
    id_tarifa     SERIAL PRIMARY KEY,
    id_servicio   INT NOT NULL REFERENCES servicio(id_servicio)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    -- NULL = tarifa general del servicio; con valor = tarifa propia de ese médico
    id_personal   INT REFERENCES personal_medico(id_personal)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    monto_vigente NUMERIC(10,2) NOT NULL
                      CHECK (monto_vigente >= 0),
    activa        BOOLEAN NOT NULL DEFAULT TRUE
);

-- Nunca puede haber dos tarifas "activas" al mismo tiempo para el mismo
-- servicio (y, si aplica, el mismo médico) — si no, no se sabría cuál usar.
CREATE UNIQUE INDEX uq_tarifa_activa_general
    ON tarifa (id_servicio)
    WHERE (activa AND id_personal IS NULL);

CREATE UNIQUE INDEX uq_tarifa_activa_personal
    ON tarifa (id_servicio, id_personal)
    WHERE (activa AND id_personal IS NOT NULL);

CREATE INDEX idx_tarifa_servicio ON tarifa(id_servicio);
CREATE INDEX idx_tarifa_personal ON tarifa(id_personal);

-- =====================================================================
-- INFRAESTRUCTURA (continuación) — Cama depende de Servicio
-- =====================================================================

CREATE TABLE cama (
    id_cama              SERIAL PRIMARY KEY,
    id_habitacion        INT NOT NULL REFERENCES habitacion(id_habitacion)
                             ON UPDATE CASCADE ON DELETE RESTRICT,
    -- Servicio de "día de estancia" que se factura mientras esta cama esté
    -- ocupada (ej. día UCI, día habitación privada, día habitación general)
    id_servicio_estancia INT REFERENCES servicio(id_servicio)
                             ON UPDATE CASCADE ON DELETE RESTRICT,
    codigo               VARCHAR(10) NOT NULL,
    estado_operativo     VARCHAR(20) NOT NULL
                             CHECK (estado_operativo IN ('Disponible', 'Ocupada', 'Limpieza', 'Mantenimiento'))
);

CREATE INDEX idx_cama_habitacion        ON cama(id_habitacion);
CREATE INDEX idx_cama_servicio_estancia ON cama(id_servicio_estancia);

-- =====================================================================
-- AGENDA
-- =====================================================================

CREATE TABLE cita (
    id_cita     SERIAL PRIMARY KEY,
    id_paciente INT NOT NULL REFERENCES paciente(id_paciente)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
    id_personal INT NOT NULL REFERENCES personal_medico(id_personal)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
    fecha       DATE NOT NULL,
    hora        TIME NOT NULL,
    estado      VARCHAR(20) NOT NULL DEFAULT 'Programada'
                    CHECK (estado IN ('Programada', 'Confirmada', 'Cancelada', 'Atendida', 'No_asistio')),
    motivo      VARCHAR(200)
);

-- =====================================================================
-- ATENCION (eje central)
-- =====================================================================

CREATE TABLE atencion (
    id_atencion   SERIAL PRIMARY KEY,
    id_paciente   INT NOT NULL REFERENCES paciente(id_paciente)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    id_personal   INT NOT NULL REFERENCES personal_medico(id_personal)
                      ON UPDATE CASCADE ON DELETE RESTRICT,
    -- UNIQUE: relación 1:1 cita -> atencion (NULL no cuenta como duplicado;
    -- cubre emergencias sin cita previa)
    id_cita       INT UNIQUE REFERENCES cita(id_cita)
                      ON UPDATE CASCADE ON DELETE SET NULL,
    tipo_atencion VARCHAR(20) NOT NULL
                      CHECK (tipo_atencion IN ('CONSULTA', 'INGRESO')),
    fecha_hora    TIMESTAMP NOT NULL DEFAULT now(),
    -- Observaciones libres de la atención (NO es lista de cobros ni de
    -- diagnósticos; esos ya tienen sus propias tablas)
    detalle       VARCHAR(300)
);

CREATE INDEX idx_atencion_paciente ON atencion(id_paciente);
CREATE INDEX idx_atencion_personal ON atencion(id_personal);

-- Ingreso: extensión 1:1 de Atencion — solo existe si tipo_atencion = 'INGRESO'
CREATE TABLE ingreso (
    id_atencion       INT PRIMARY KEY REFERENCES atencion(id_atencion)
                          ON UPDATE CASCADE ON DELETE CASCADE,
    id_cama           INT NOT NULL REFERENCES cama(id_cama)
                          ON UPDATE CASCADE ON DELETE RESTRICT,
    fecha_hora_ingreso TIMESTAMP NOT NULL,
    tipo              VARCHAR(20) NOT NULL
                          CHECK (tipo IN ('Emergencia', 'Programado', 'Traslado')),
    fecha_hora_alta   TIMESTAMP,
    motivo_alta       VARCHAR(100),
    CHECK (fecha_hora_alta IS NULL OR fecha_hora_alta >= fecha_hora_ingreso)
);

-- Trigger: consistencia entre atencion.tipo_atencion e ingreso
CREATE OR REPLACE FUNCTION fn_validar_tipo_atencion_ingreso()
RETURNS TRIGGER AS $$
BEGIN
    IF (SELECT tipo_atencion FROM atencion WHERE id_atencion = NEW.id_atencion) <> 'INGRESO' THEN
        RAISE EXCEPTION 'No se puede crear un Ingreso para una Atencion cuyo tipo_atencion no es INGRESO (id_atencion=%)', NEW.id_atencion;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validar_tipo_atencion_ingreso
    BEFORE INSERT OR UPDATE ON ingreso
    FOR EACH ROW EXECUTE FUNCTION fn_validar_tipo_atencion_ingreso();

-- =====================================================================
-- EXPEDIENTE CLÍNICO
-- =====================================================================

CREATE TABLE diagnostico (
    id_diagnostico SERIAL PRIMARY KEY,
    id_atencion    INT NOT NULL REFERENCES atencion(id_atencion)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    descripcion    VARCHAR(300) NOT NULL
);

CREATE TABLE tratamiento (
    id_tratamiento SERIAL PRIMARY KEY,
    id_diagnostico INT NOT NULL REFERENCES diagnostico(id_diagnostico)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    descripciones  VARCHAR(500),
    observaciones  VARCHAR(300),
    estado         VARCHAR(20) NOT NULL DEFAULT 'Activo'
                       CHECK (estado IN ('Activo', 'Finalizado', 'Suspendido')),
    fecha_inicio   DATE,
    fecha_fin      DATE,
    CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
);

CREATE INDEX idx_diagnostico_atencion ON diagnostico(id_atencion);

-- =====================================================================
-- ÓRDENES Y RECETAS
-- =====================================================================

CREATE TABLE orden_medica (
    id_orden    SERIAL PRIMARY KEY,
    id_atencion INT NOT NULL REFERENCES atencion(id_atencion)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
    id_personal INT NOT NULL REFERENCES personal_medico(id_personal)
                    ON UPDATE CASCADE ON DELETE RESTRICT,
    fecha_hora  TIMESTAMP NOT NULL DEFAULT now(),
    tipo_orden  VARCHAR(20) NOT NULL
                    CHECK (tipo_orden IN ('Medicamento', 'Examen', 'Procedimiento', 'Interconsulta'))
);

CREATE INDEX idx_orden_atencion ON orden_medica(id_atencion);

CREATE TABLE receta (
    id_receta  SERIAL PRIMARY KEY,
    id_orden   INT NOT NULL REFERENCES orden_medica(id_orden)
                   ON UPDATE CASCADE ON DELETE RESTRICT,
    fecha_hora TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE detalle_receta (
    id_detalle   SERIAL PRIMARY KEY,
    id_receta    INT NOT NULL REFERENCES receta(id_receta)
                     ON UPDATE CASCADE ON DELETE CASCADE,
    medicamento  VARCHAR(150) NOT NULL,
    dosis        VARCHAR(50),
    frecuencia   VARCHAR(50),
    duracion     VARCHAR(50),
    cantidad     INT CHECK (cantidad IS NULL OR cantidad > 0),
    indicaciones VARCHAR(300)
);

-- =====================================================================
-- MÓDULO DE PAGOS — cobro, detalle y pagos
-- =====================================================================

CREATE TABLE cobro (
    id_cobro       SERIAL PRIMARY KEY,
    id_atencion    INT NOT NULL REFERENCES atencion(id_atencion)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    fecha_apertura TIMESTAMP NOT NULL DEFAULT now(),
    fecha_cierre   TIMESTAMP,
    estado         VARCHAR(20) NOT NULL DEFAULT 'Abierto'
                       CHECK (estado IN ('Abierto', 'Cerrado', 'Pagado', 'Anulado')),
    CHECK (fecha_cierre IS NULL OR fecha_cierre >= fecha_apertura)
);

CREATE INDEX idx_cobro_atencion ON cobro(id_atencion);

CREATE TABLE detalle_cobro (
    id_detalle_cobro        SERIAL PRIMARY KEY,
    id_cobro                INT NOT NULL REFERENCES cobro(id_cobro)
                                 ON UPDATE CASCADE ON DELETE CASCADE,
    id_tarifa                INT NOT NULL REFERENCES tarifa(id_tarifa)
                                 ON UPDATE CASCADE ON DELETE RESTRICT,
    fecha_hora_servicio      TIMESTAMP NOT NULL DEFAULT now(),
    descripcion_aplicada     VARCHAR(200),
    cantidad                 INT NOT NULL DEFAULT 1
                                 CHECK (cantidad > 0),
    -- "Congelado" del monto_vigente de la tarifa al momento de facturar;
    -- no cambia si la tarifa cambia después.
    precio_unitario_aplicado NUMERIC(10,2) NOT NULL
                                 CHECK (precio_unitario_aplicado >= 0),
    -- Columna calculada: PostgreSQL la mantiene consistente sola.
    monto NUMERIC(10,2) GENERATED ALWAYS AS (cantidad * precio_unitario_aplicado) STORED
);

CREATE INDEX idx_detalle_cobro_cobro  ON detalle_cobro(id_cobro);
CREATE INDEX idx_detalle_cobro_tarifa ON detalle_cobro(id_tarifa);

CREATE TABLE metodo_pago (
    id_metodo_pago SERIAL PRIMARY KEY,
    nombre         VARCHAR(30) NOT NULL UNIQUE
                       CHECK (nombre IN ('Efectivo', 'Tarjeta', 'Transferencia', 'Cheque'))
);

INSERT INTO metodo_pago (nombre) VALUES ('Efectivo'), ('Tarjeta'), ('Transferencia'), ('Cheque');

CREATE TABLE pago (
    id_pago        SERIAL PRIMARY KEY,
    id_cobro       INT NOT NULL REFERENCES cobro(id_cobro)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    id_metodo_pago INT NOT NULL REFERENCES metodo_pago(id_metodo_pago)
                       ON UPDATE CASCADE ON DELETE RESTRICT,
    monto          NUMERIC(10,2) NOT NULL
                       CHECK (monto > 0),
    fecha_hora     TIMESTAMP NOT NULL DEFAULT now(),
    estado         VARCHAR(20) NOT NULL DEFAULT 'Confirmado'
                       CHECK (estado IN ('Confirmado', 'Anulado'))
);

CREATE INDEX idx_pago_cobro ON pago(id_cobro);

-- Trigger: la suma de pagos CONFIRMADOS no puede superar el total
-- facturado en Detalle_Cobro para ese Cobro (integridad transaccional
-- fuerte — el mismo argumento que justifica PostgreSQL en el documento
-- comparativo del proyecto).
CREATE OR REPLACE FUNCTION fn_validar_pago_no_excede_total()
RETURNS TRIGGER AS $$
DECLARE
    v_total  NUMERIC(10,2);
    v_pagado NUMERIC(10,2);
BEGIN
    SELECT COALESCE(SUM(monto), 0) INTO v_total
        FROM detalle_cobro WHERE id_cobro = NEW.id_cobro;

    SELECT COALESCE(SUM(monto), 0) INTO v_pagado
        FROM pago WHERE id_cobro = NEW.id_cobro AND estado = 'Confirmado';

    IF NEW.estado = 'Confirmado' AND (v_pagado + NEW.monto) > v_total THEN
        RAISE EXCEPTION 'El pago (%) excede el saldo pendiente del cobro % (total=%, ya pagado=%)',
            NEW.monto, NEW.id_cobro, v_total, v_pagado;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validar_pago_no_excede_total
    BEFORE INSERT ON pago
    FOR EACH ROW EXECUTE FUNCTION fn_validar_pago_no_excede_total();

-- =====================================================================
-- ÍNDICES DE APOYO ADICIONALES
-- =====================================================================

CREATE INDEX idx_cita_paciente   ON cita(id_paciente);
CREATE INDEX idx_paciente_dpi    ON paciente(dpi);
CREATE INDEX idx_paciente_estado ON paciente(estado);
CREATE INDEX idx_paciente_encargado ON paciente(id_encargado);

-- =====================================================================
-- COMENTARIOS — clasificación pública / confidencial / restringida
-- =====================================================================

COMMENT ON COLUMN encargado.dpi               IS 'Confidencial';
COMMENT ON COLUMN encargado.telefono          IS 'Confidencial';

COMMENT ON COLUMN paciente.dpi                IS 'Confidencial';
COMMENT ON COLUMN paciente.fecha_nacimiento   IS 'Confidencial';
COMMENT ON COLUMN paciente.grupo_sanguineo    IS 'Confidencial';
COMMENT ON COLUMN paciente.telefono           IS 'Confidencial';
COMMENT ON COLUMN paciente.direccion          IS 'Confidencial';
COMMENT ON COLUMN paciente.correo_electronico IS 'Confidencial';
COMMENT ON COLUMN paciente.estado             IS 'Activo = en servicio; Inactivo = dado de baja (traslado, fallecimiento u otra causa administrativa)';
COMMENT ON COLUMN paciente.fecha_baja         IS 'Restringido. Obligatoria si estado = Inactivo';
COMMENT ON COLUMN paciente.motivo_baja        IS 'Restringido. Obligatoria si estado = Inactivo';

COMMENT ON COLUMN personal_medico.colegiado IS 'Confidencial';
COMMENT ON COLUMN personal_medico.telefono  IS 'Confidencial';
COMMENT ON COLUMN personal_medico.correo    IS 'Confidencial';

COMMENT ON COLUMN tarifa.monto_vigente              IS 'Restringido';
COMMENT ON COLUMN detalle_cobro.precio_unitario_aplicado IS 'Restringido';
COMMENT ON COLUMN detalle_cobro.monto               IS 'Restringido';
COMMENT ON COLUMN pago.monto                        IS 'Restringido';

COMMENT ON COLUMN diagnostico.descripcion     IS 'Confidencial';
COMMENT ON COLUMN tratamiento.descripciones   IS 'Confidencial';
COMMENT ON COLUMN tratamiento.observaciones   IS 'Confidencial';
COMMENT ON COLUMN detalle_receta.indicaciones IS 'Confidencial';
COMMENT ON COLUMN atencion.detalle            IS 'Confidencial';

COMMIT;
