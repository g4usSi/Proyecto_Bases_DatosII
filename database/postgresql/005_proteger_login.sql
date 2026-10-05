-- Compatible con una inicializacion anterior de esta misma base.
ALTER TABLE identidad.profesional ADD COLUMN IF NOT EXISTS fallos_login INTEGER NOT NULL DEFAULT 0
  CHECK (fallos_login >= 0);
ALTER TABLE identidad.profesional ADD COLUMN IF NOT EXISTS bloqueado_hasta TIMESTAMPTZ;
GRANT UPDATE(fallos_login, bloqueado_hasta) ON identidad.profesional TO historiales_app;
