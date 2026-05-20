# Alembic Multi-Database Migrations

## Status

`implemented`

## Source task

User request: configure Alembic for multi-database migrations on the Warehouse project.

The multi-tenant architecture has two levels:

1. **`aton_clients`** — shared database, the client registry (table `clients`).
2. **`client_{slug}`** — a separate database per client (the tenant schema), provisioned from a
   `client_template`.

Alembic must support both databases with **separate migration histories**.

## Scope

Create an Alembic setup that drives two independent migration lineages from a single repo, selected
by the Alembic config-section name (`alembic -n <section>`):

```
alembic/
  env.py               ← custom multi-DB env
  script.py.mako       ← standard revision template
  versions/
    aton_clients/      ← migrations for the shared registry DB
    client_template/   ← migrations for the per-tenant template DB
alembic.ini
```

### `alembic.ini`

- `[alembic]` section with `script_location = alembic` (shared defaults: logging, file template).
- `[aton_clients]` section — its own `version_locations = alembic/versions/aton_clients` and a
  marker telling `env.py` which logical database to target.
- `[client_template]` section — its own `version_locations = alembic/versions/client_template` and
  its database marker.
- **No hardcoded connection strings.** `sqlalchemy.url` is left blank / a placeholder; the real URL
  is resolved at runtime in `env.py` from the app `Settings` (env vars). This satisfies the
  "reads from env vars" requirement and reuses the single source of truth in `settings.py`.
- Standard `[loggers]` / `[handlers]` / `[formatters]` logging blocks (use the `logging` module,
  per RULES.md — never `print`).

### `alembic/env.py`

Custom multi-DB env exposing:

- `run_migrations_for_db(db_name: str, versions_path: str) -> None`
  Core routine. Runs migrations for one concrete database. Dispatches to offline vs online based on
  `context.is_offline_mode()`, and points `version_locations` at `versions_path` so each lineage
  keeps its own history and `alembic_version` table.
- `run_aton_clients() -> None`
  Resolves the shared registry DB name (`aton_clients`, sourced from `Settings.app_postgres_db` /
  a dedicated setting) and calls `run_migrations_for_db(db_name, "alembic/versions/aton_clients")`.
- `run_client_template() -> None`
  Resolves the tenant template DB name (`client_template`) and calls
  `run_migrations_for_db(db_name, "alembic/versions/client_template")`.
- Offline mode: build the DSN string from `Settings` and call
  `context.configure(url=..., literal_binds=True, ...)` then emit SQL.
- Online mode: obtain an engine via **`get_engine(db_name)` from `app.infrastructure.database`**
  (per task requirement), then run migrations against a live connection.

#### Async engine handling (decision)

`get_engine()` returns an **`AsyncEngine`** (asyncpg). Alembic's `context.run_migrations()` is
synchronous and cannot run directly on an async connection. The env will bridge this with
`asyncio.run(...)` + `connection.run_sync(do_run_migrations)` (the standard Alembic async recipe),
reusing the project's existing `AsyncEngine` from `get_engine()` rather than building a second
sync engine. This keeps a single engine factory / single source of connection config, as required.

#### Section selection

`env.py` reads the active config section name via `context.config.config_ini_section`
(set by `alembic -n <name>`) and routes:

- `aton_clients` → `run_aton_clients()`
- `client_template` → `run_client_template()`

A small mapping table (section name → handler) keeps this explicit and avoids string-magic.

### `script.py.mako`

Standard Alembic revision template (the default generated one), unmodified, so
`alembic -n <section> revision -m "..."` produces revision files in the section's
`version_locations` directory.

### Database name resolution (decision)

- `aton_clients` is already the value of `APP_POSTGRES_DB` in `.env`, and `init-db.sql` guarantees
  that database exists. The shared lineage targets `aton_clients`.
- `client_template` is a **separate physical database** used as the prototype for each
  `client_{slug}` tenant DB. It does not exist yet in `init-db.sql`.

Two sub-decisions to confirm at approval:

1. **Where the DB names come from.** Recommended: add two settings — `alembic_shared_db`
   (default `aton_clients`) and `alembic_template_db` (default `client_template`) — to `Settings`,
   so names are not hardcoded in `env.py`. Alternative: hardcode the two literal names in `env.py`
   (simpler, but less consistent with the "no hardcoding" principle for DB identity).
2. **Whether to also create the `client_template` database.** The task only asks for Alembic config,
   not provisioning. Recommended: add a `CREATE DATABASE client_template` guard to
   `docker/init-db.sql` (mirroring the existing `aton_clients` guard) so `alembic -n client_template
   upgrade head` has a database to connect to. This is a minimal, in-scope-adjacent change. If the
   user prefers to keep init-db.sql untouched, the implementer will instead document that the
   template DB must be created manually before running its migrations.

## Out of scope

- Writing any actual migration revisions (no `clients` table migration, no tenant schema tables).
  Only the empty `versions/aton_clients` and `versions/client_template` directories (with
  `.keep` placeholders) are created. First revisions are separate, later tasks.
- Per-tenant `client_{slug}` runtime provisioning / cloning logic (creating a new tenant DB from the
  template). This is application/service code, not Alembic config.
- A tenant DB router or registry-driven "run migrations across all tenant DBs" loop. The task targets
  the `client_template` lineage; fanning a tenant migration out to every live `client_{slug}` DB is a
  later orchestration task.
- Wiring Alembic into CI or app startup.
- Changing PgBouncer / docker-compose service definitions (beyond the optional init-db.sql DB guard).

## Acceptance criteria

- Directory layout exists exactly as specified (`alembic/env.py`, `alembic/script.py.mako`,
  `alembic/versions/aton_clients/`, `alembic/versions/client_template/`, `alembic.ini`).
- `alembic.ini` has `[alembic]`, `[aton_clients]`, and `[client_template]` sections; no hardcoded
  connection string is present (URL resolved at runtime from env).
- `env.py` defines `run_migrations_for_db(db_name, versions_path)`, `run_aton_clients()`, and
  `run_client_template()`, and supports both offline and online modes.
- Online mode obtains its engine via `get_engine()` from `app.infrastructure.database`.
- `alembic -n aton_clients revision -m "init"` creates a revision under
  `alembic/versions/aton_clients/` (separate history).
- `alembic -n client_template revision -m "init"` creates a revision under
  `alembic/versions/client_template/` (separate, independent history).
- `alembic -n aton_clients upgrade head` and `alembic -n client_template upgrade head` connect to the
  correct database and apply their own lineage (verifiable once the Docker stack + a first revision
  exist; structural correctness verified without live DB).
- `alembic -n aton_clients upgrade head --sql` (offline) emits SQL without a live connection.
- No `print()`; type hints on all `env.py` function signatures; no hardcoded secrets.

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `alembic.ini` | created | implementer |
| `alembic/env.py` | created | implementer |
| `alembic/script.py.mako` | created | implementer |
| `alembic/versions/aton_clients/.keep` | created | implementer |
| `alembic/versions/client_template/.keep` | created | implementer |
| `app/infrastructure/settings.py` | updated (optional: `alembic_shared_db` / `alembic_template_db` fields) | implementer |
| `docker/init-db.sql` | updated (optional: add `client_template` DB guard) | implementer |
| `.env` | updated only if new settings need values (defaults cover it; likely no change) | implementer |
| `docs/plans/2026-05-20-alembic-multi-db-migrations.md` | status → `implemented` after build | docs-writer |

## Risks

- **Async vs sync Alembic.** `get_engine()` is async (asyncpg). The env must use the
  `run_sync` bridge; getting this wrong yields "coroutine was never awaited" or hangs. Mitigated by
  using the documented async Alembic recipe and reusing the existing engine factory.
- **PgBouncer transaction pooling + DDL.** Migrations run DDL through PgBouncer (port 6432,
  transaction mode). DDL across multiple statements should run inside one transaction per Alembic's
  default; `prepared_statement_cache_size=0` is already set in `get_engine`. Low risk, but worth a
  note. If issues arise, an option is to run migrations directly against PostgreSQL (5432) instead of
  PgBouncer — flag for the user if they want that as the migration path.
- **`client_template` database may not exist**, causing `upgrade head` to fail on connect. Mitigated
  by the optional `init-db.sql` guard (decision above).
- **`version_locations` separation.** If both sections shared one versions dir, histories would
  collide. Mitigated by per-section `version_locations` and per-DB `alembic_version` table (each DB
  has its own). Reviewer must confirm the two lineages cannot cross-contaminate.
- **Single source of config.** Resolving the DSN from `Settings` (not `alembic.ini`) is the
  intended design; reviewer should confirm `alembic.ini` has no live credentials.

## Agent decisions

- **planner**: this plan (no code written).
- **ui-designer**: not required (no UI scope).
- **database**: **not required for this task as scoped.** Rationale: this task is Alembic *tooling /
  config* (env.py wiring, ini sections, directory layout), not schema design — no tables, columns, or
  indexes are being designed or migrated here. The database agent becomes required for the *first
  actual revisions* (`clients` table, tenant schema), which are explicitly out of scope. If the user
  wants the optional `init-db.sql` `client_template` guard treated as a schema change, the database
  agent can own that one-line guard; otherwise implementer handles it as infra config. Recommend
  implementer owns it.
- **implementer**: owns all created/updated files above.
- **reviewer**: verify the two lineages are fully independent (separate `version_locations`,
  separate `alembic_version`), offline+online both work, online uses `get_engine()`, async bridge is
  correct, no hardcoded credentials, type hints, no `print`.
- **security**: **recommended.** Touches DB connection/trust boundary and credential resolution
  (DSN built from secrets). Run after reviewer to confirm no secret leaks into `alembic.ini` or
  generated SQL, and that migrations target the correct tenant DB (no cross-tenant DDL).
- **docs-writer**: update this plan status to `implemented` and record what was built; add a short
  "running migrations" note to the relevant `docs/application-stack` doc if one covers DB ops.
- **spec-writer**: not required (developer tooling, no end-user-facing functionality).
- **version-control**: commit plan + Alembic files together at the end.

## Open questions for approval

1. **DB-name source**: add `alembic_shared_db` / `alembic_template_db` settings (recommended) vs.
   hardcode `aton_clients` / `client_template` literals in `env.py`?
2. **`client_template` provisioning**: add a `CREATE DATABASE client_template` guard to
   `docker/init-db.sql` (recommended) vs. leave init-db.sql untouched and document manual creation?
3. **Migration connection target**: run migrations through PgBouncer (6432, current `get_engine`
   default) vs. directly against PostgreSQL (5432)? Recommended: keep `get_engine`/PgBouncer for
   consistency unless DDL pooling issues surface.

## What was built

- `alembic.ini` — root config with `[alembic]`, `[aton_clients]`, and `[client_template]` sections.
  No connection strings; standard logging blocks included.
- `alembic/env.py` — custom multi-DB env with `get_dsn`, `run_migrations_offline`,
  `run_migrations_online`, `run_migrations_for_db`, `run_aton_clients`, `run_client_template`.
  Online mode uses `get_engine()` from `app.infrastructure.database` and the `asyncio.run` +
  `connection.run_sync` async bridge. Section dispatch via `_SECTION_HANDLERS` mapping.
- `alembic/script.py.mako` — standard Alembic revision template.
- `alembic/versions/aton_clients/.keep` — placeholder for the shared registry migration lineage.
- `alembic/versions/client_template/.keep` — placeholder for the tenant template migration lineage.
- `app/infrastructure/settings.py` — two new fields added: `alembic_shared_db = "aton_clients"` and
  `alembic_template_db = "client_template"`.
- `docker/init-db.sql` — `CREATE DATABASE client_template` guard appended (mirrors existing
  `aton_clients` guard).

All open questions resolved with recommended defaults: settings-based DB name resolution, init-db.sql
guard added, migrations run through `get_engine` (PgBouncer path).

## Approval log

- 2026-05-20: plan drafted, awaiting user approval. Three open questions above must be answered (or
  defaults accepted) before implementation starts.
- 2026-05-20: plan approved, implementation completed.
