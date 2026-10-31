-- Local demonstration only. Migrations run as the schema owner; FastAPI runs as this restricted role.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'nodeswarm_app') THEN
    CREATE ROLE nodeswarm_app LOGIN PASSWORD 'nodeswarm_app_dev_only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END
$$;

GRANT CONNECT ON DATABASE nodeswarm TO nodeswarm_app;
GRANT USAGE ON SCHEMA public TO nodeswarm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE nodeswarm IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO nodeswarm_app;
