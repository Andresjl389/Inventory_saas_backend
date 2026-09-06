-- Runs once, as the container superuser, when the data directory is created.
--
-- The point of this file is the application role: PostgreSQL superusers bypass
-- Row Level Security unconditionally, so the app must never connect as one.
-- `inventory` is NOSUPERUSER + NOBYPASSRLS and owns the schema, and every
-- tenant table is created with FORCE ROW LEVEL SECURITY so the policies apply
-- to the owner as well.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'inventory') THEN
        CREATE ROLE inventory
            LOGIN PASSWORD 'inventory'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;

ALTER DATABASE inventory OWNER TO inventory;
ALTER SCHEMA public OWNER TO inventory;
GRANT ALL ON SCHEMA public TO inventory;
