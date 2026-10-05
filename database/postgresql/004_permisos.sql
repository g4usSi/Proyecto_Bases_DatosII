-- El backend no se conecta como superusuario. Secreto leido del entorno del contenedor.
\getenv app_password POSTGRES_APP_PASSWORD
CREATE ROLE historiales_app LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE hospital_general TO historiales_app;
GRANT USAGE ON SCHEMA public, identidad TO historiales_app;
GRANT SELECT ON public.paciente TO historiales_app;
GRANT SELECT ON ALL TABLES IN SCHEMA identidad TO historiales_app;
GRANT UPDATE(version_token) ON identidad.profesional TO historiales_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
