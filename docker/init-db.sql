-- ---------------------------------------------------------------------------
-- PostgreSQL init script (runs only on first container start, empty data dir).
-- The primary database (POSTGRES_DB) is created automatically by the image.
-- This script guarantees the `aton_clients` database exists even if
-- POSTGRES_DB is set to a different value, and is the place to add any
-- bootstrap that must run before Alembic migrations.
--
-- RLS, tenant tables, and schema are added later via Alembic migrations.
-- ---------------------------------------------------------------------------

SELECT 'CREATE DATABASE aton_clients'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'aton_clients')
\gexec

SELECT 'CREATE DATABASE client_template'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'client_template')
\gexec
