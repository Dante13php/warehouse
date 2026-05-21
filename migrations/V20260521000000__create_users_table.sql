-- ---------------------------------------------------------------------------
-- V20260521000000__create_users_table.sql
--
-- Standalone reference DDL for the per-tenant `users` table. The CANONICAL
-- migration for this project is the Alembic client_template revision
-- alembic/versions/client_template/20260521_0000_0001_create_users_table.py
-- (apply with: alembic -n client_template upgrade head). This file mirrors that
-- revision as a plain psql-runnable script for environments without Alembic,
-- and follows the database-agent migration convention (idempotent, rollback at
-- the bottom).
--
-- Run against each per-tenant database (client_template and every client_{slug}).
-- Execute via: psql -U <user> -d <database> -f migrations/V20260521000000__create_users_table.sql
--
-- Design (docs/plans/2026-05-20-users-endpoint.md, FINAL answers):
--   id            BIGINT IDENTITY (auto-increment integer, NOT UUID)   [Q3]
--   email         TEXT, UNIQUE (tenant_id, email) -> per-tenant unique [Q4]
--   role          user_role ENUM ('manager','staff')
--   RLS           tenant isolation on app.tenant_id GUC, permissive-     [Q5]
--                 until-wired (allows when GUC unset) so reads do not
--                 silently return 0 rows before tenant routing exists.
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
-- ROLLBACK (run manually to revert this migration):
--
-- DROP POLICY IF EXISTS tenant_isolation ON users;
-- DROP TABLE IF EXISTS users;
-- DROP TYPE IF EXISTS user_role;
-- ---------------------------------------------------------------------------
