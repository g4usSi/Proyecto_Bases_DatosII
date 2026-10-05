-- Vinculo logico con la identidad central, no obliga a dar login a todo registro historico.
ALTER TABLE public.personal_medico ADD COLUMN id_profesional_central UUID UNIQUE
  REFERENCES identidad.profesional(id_profesional);
COMMENT ON COLUMN public.personal_medico.id_profesional_central
  IS 'Identidad de acceso; verificar pertenencia al hospital desde la API';
