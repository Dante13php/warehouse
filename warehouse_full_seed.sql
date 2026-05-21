-- ===========================================================================
-- warehouse_full_seed.sql
--
-- Backup / reference PostgreSQL script: full schema + dev-only seed data for a
-- single per-tenant Warehouse database (client_template lineage). This is the
-- RULES-mandated companion to the Alembic migrations
-- ("New tables require warehouse_full_seed.sql updates with schema and seed
-- data"). The CANONICAL schema source remains the Alembic client_template
-- revisions under alembic/versions/client_template/; this file mirrors the
-- current applied state so a tenant DB can be reconstructed from one script.
--
-- Run against a per-tenant database (NOT the aton_clients registry):
--   psql -U <user> -d client_template -f warehouse_full_seed.sql
--
-- !!! DEV / LOCAL ONLY !!!
-- The seed credentials below are placeholder development credentials. They are
-- NOT secrets and MUST NOT be used in any shared or production environment.
-- The seed block is guarded so it can be skipped in non-dev contexts.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- SCHEMA
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'user_role') THEN
        CREATE TYPE user_role AS ENUM ('manager', 'staff');
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id UUID NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role user_role NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_tenant_email UNIQUE (tenant_id, email)
);

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'users'
          AND policyname = 'tenant_isolation'
    ) THEN
        CREATE POLICY tenant_isolation ON users
        USING (
            current_setting('app.tenant_id', true) IS NULL
            OR current_setting('app.tenant_id', true) = ''
            OR tenant_id::text = current_setting('app.tenant_id', true)
        )
        WITH CHECK (
            current_setting('app.tenant_id', true) IS NULL
            OR current_setting('app.tenant_id', true) = ''
            OR tenant_id::text = current_setting('app.tenant_id', true)
        );
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- SEED (DEV / LOCAL ONLY)
--
-- One placeholder manager and one placeholder staff user for a sample tenant.
-- password_hash below is bcrypt('123456') -- the numeric PIN dev login.
-- tenant_id is a fixed sample UUID for local development only.
--
-- To run with seed data:        psql ... -v seed_dev=1 -f warehouse_full_seed.sql
-- To run schema-only (default): psql ...                -f warehouse_full_seed.sql
-- ---------------------------------------------------------------------------

\if :{?seed_dev}
    INSERT INTO users (tenant_id, email, password_hash, role)
    VALUES
        (
            '00000000-0000-0000-0000-000000000001',
            'manager@dev.local',
            '$2b$12$spdHB.dt1neeHN6hnZGNU.61sBAgauXk9JXzwngplTkjGpdbgoqmu',
            'manager'
        ),
        (
            '00000000-0000-0000-0000-000000000001',
            'staff@dev.local',
            '$2b$12$spdHB.dt1neeHN6hnZGNU.61sBAgauXk9JXzwngplTkjGpdbgoqmu',
            'staff'
        )
    ON CONFLICT (tenant_id, email) DO NOTHING;
\endif
