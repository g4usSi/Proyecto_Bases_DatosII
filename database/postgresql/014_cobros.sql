-- Hospital General: cobros y pagos desde la API sobre el modulo de pagos original
-- (servicio, tarifa, cobro, detalle_cobro, metodo_pago, pago) con las reglas de 010.
--   * pagos:ver       -> ver cobros, cargos, pagos y saldos (montos restringidos);
--   * pagos:registrar -> abrir cobros, agregar cargos, registrar y anular pagos, cerrar o
--                        anular cobros.
-- La cuenta de la API no borra nada: un pago se anula y un cobro se anula sin pagos.
-- Aditivo e idempotente. Aplicar a mano en una base existente (PowerShell, desde la raiz):
--   Get-Content database\postgresql\014_cobros.sql | docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U historiales_admin -d hospital_general
BEGIN;
SET LOCAL client_min_messages = warning;

INSERT INTO identidad.permiso(codigo) VALUES ('pagos:ver'), ('pagos:registrar')
ON CONFLICT DO NOTHING;

ALTER TABLE cobro ADD COLUMN IF NOT EXISTS descripcion VARCHAR(300);
-- Numero de comprobante o autorizacion; nunca datos de tarjeta.
ALTER TABLE pago ADD COLUMN IF NOT EXISTS referencia VARCHAR(150);
COMMENT ON COLUMN pago.referencia IS 'Comprobante o autorizacion; nunca datos de tarjeta';
CREATE INDEX IF NOT EXISTS idx_cobro_estado ON cobro(estado, fecha_apertura);

GRANT SELECT ON servicio, tarifa, metodo_pago, cobro, detalle_cobro, pago TO historiales_app;
GRANT INSERT ON cobro, detalle_cobro, pago TO historiales_app;
GRANT UPDATE (estado, fecha_cierre) ON cobro TO historiales_app;
GRANT UPDATE (estado) ON pago TO historiales_app;
GRANT USAGE ON SEQUENCE cobro_id_cobro_seq, detalle_cobro_id_detalle_cobro_seq, pago_id_pago_seq
  TO historiales_app;

COMMIT;
