# Infrastructure Layer

## Status

`implemented`

## Source task

User request: implement the Infrastructure layer of the Warehouse project under `app/infrastructure/`.
The FastAPI app runs locally and connects to PgBouncer (DB) and Redis, both running in Docker.

## Scope

Create the application infrastructure layer in `app/infrastructure/`:

1. `settings.py` — Pydantic Settings (`pydantic-settings`) loaded from `.env`, exposed via an
   `lru_cache`-backed `get_settings()` singleton.
2. `database.py` — async SQLAlchemy engine factory with per-`db_name` engine caching, asyncpg
   `connect_args` configured for PgBouncer transaction pooling, an async session factory, and a
   FastAPI `get_db` dependency.
3. `redis.py` — singleton `redis.asyncio.ConnectionPool` plus a `get_redis` FastAPI dependency.
4. `transaction.py` — `TransactionHelper` with `async wrap(session, func, *args, **kwargs)` that
   commits on success and rolls back on error.

This layer is the foundation that future controllers/services/storages depend on.

## Out of scope

- Tenant DB router and `aton_clients` registry lookup (multi-tenancy router) — only the engine
  factory primitive is built here; routing tenant_id -> db_name is a later task.
- Alembic migrations and seed SQL.
- ARQ `WorkerSettings` module.
- Auth / JWT token creation & verification logic (only the JWT settings fields are loaded).
- Wiring the infrastructure into `app/main.py` (no new routes/endpoints required by this task).
- Updating `.env` credential values.

## Settings / env reconciliation (important decision)

The task spec asks for these settings fields and defaults:

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` (default `localhost`),
  `POSTGRES_PORT` (default `6432` — PgBouncer), `POSTGRES_DB`
- `REDIS_HOST` (default `localhost`), `REDIS_PORT` (default `6379`), `REDIS_PASSWORD`
- `JWT_SECRET_KEY`, `JWT_ALGORITHM` (default `HS256`), `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default `30`)

The existing `.env` already defines `POSTGRES_HOST=postgres` and `POSTGRES_PORT=5432` — these are the
**in-Docker** values used by container-to-container traffic (PgBouncer -> PostgreSQL), NOT the values
the locally-run FastAPI app should use. The app must reach PgBouncer at `localhost:6432`.

Conflict resolution: the `Settings` class will use **app-scoped env var names** so the application
config does not collide with the Docker/container vars already in `.env`. Proposed approach:

- Read DB connection from dedicated app vars with the spec defaults: `POSTGRES_HOST` default
  `localhost`, `POSTGRES_PORT` default `6432`. Because `.env` currently sets `POSTGRES_HOST=postgres`
  and `POSTGRES_PORT=5432`, the implementer will add app-facing overrides to `.env` so the local app
  resolves to `localhost:6432`. Decision to confirm at approval: either
  (A) add `APP_POSTGRES_HOST=localhost` / `APP_POSTGRES_PORT=6432` style app-prefixed vars, or
  (B) change `.env` `POSTGRES_HOST`/`POSTGRES_PORT` to the host-facing values and let Docker Compose
  use the published-port mapping it already has. **Recommended: option A (app-prefixed vars)** to
  avoid breaking the working Docker Compose stack, which consumes the existing unprefixed names.

`REDIS_HOST`, `REDIS_SECRET`/`JWT_*` are new and can be added directly (no Docker collision).
`extra="ignore"` will be set on the settings model config so unrelated `.env` keys
(`PGBOUNCER_*`, `ARQ_REDIS_URL`, `*_PUBLISHED_PORT`, etc.) do not raise validation errors.

## Implementation detail decisions

- **PgBouncer transaction pooling**: asyncpg `connect_args` will set
  `prepared_statement_cache_size=0` (mandatory) and a per-connection
  `prepared_statement_name_func` returning unique names to avoid cross-connection prepared-statement
  reuse under transaction pooling. SQLAlchemy `create_async_engine` will use `poolclass=NullPool`
  so SQLAlchemy does not also pool on top of PgBouncer.
- **Engine cache**: module-level `dict[str, AsyncEngine]` keyed by `db_name`. `get_engine(db_name)`
  lazily creates and caches.
- **Session factory**: `get_session(db_name)` returns an `async_sessionmaker`
  (`AsyncSessionLocal`) bound to the cached engine, `expire_on_commit=False`.
- **`get_db(db_name)`**: async generator dependency yielding a session, ensuring close in `finally`.
- **Redis**: module-level singleton `ConnectionPool` built from settings (host/port/password,
  `decode_responses=True`); `get_redis()` returns `redis.asyncio.Redis(connection_pool=pool)`.
- **TransactionHelper.wrap**: `async with session.begin()` semantics — await `func`, commit on
  success, rollback + re-raise on exception.
- Type hints on every signature; `logging` (not `print`); no mutable default args.

## Acceptance criteria

- `get_settings()` returns a cached singleton; repeated calls return the same instance.
- Settings load from `.env` without raising on the existing unrelated keys.
- DB DSN resolves to `postgresql+asyncpg://<user>:<pass>@<host>:<port>/<db_name>` and, with the
  configured app env, targets `localhost:6432`.
- `get_engine(db_name)` returns the same `AsyncEngine` instance on repeated calls for the same
  `db_name`, and distinct engines for different names.
- asyncpg `connect_args` includes `prepared_statement_cache_size=0`; engine uses `NullPool`.
- `get_session(db_name)` produces working `AsyncSession`s; `get_db(db_name)` is an async generator
  that closes the session.
- `get_redis_pool()` returns a singleton `ConnectionPool`; `get_redis()` returns a `Redis` bound to
  it.
- `TransactionHelper.wrap` commits on success and rolls back + re-raises on error.
- `python -c "import app.infrastructure.settings, app.infrastructure.database, app.infrastructure.redis, app.infrastructure.transaction"` imports cleanly.

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `app/infrastructure/settings.py` | created | implementer |
| `app/infrastructure/database.py` | created | implementer |
| `app/infrastructure/redis.py` | created | implementer |
| `app/infrastructure/transaction.py` | created | implementer |
| `app/infrastructure/__init__.py` | updated (optional re-exports) | implementer |
| `.env` | updated (add app-facing DB host/port + Redis host + JWT vars) | implementer |

## Risks

- **Env var collision** between Docker Compose vars and app vars (`POSTGRES_HOST`/`POSTGRES_PORT`).
  Mitigated by app-prefixed vars (option A). Needs explicit user confirmation.
- **PgBouncer transaction pooling**: forgetting `prepared_statement_cache_size=0` or SQLAlchemy
  pooling on top would cause "prepared statement already exists" errors at runtime. Enforced in the
  engine factory.
- **JWT_SECRET_KEY** has no safe default; if absent from `.env` settings will fail to load. The
  implementer adds a dev placeholder to `.env`.
- Cannot fully runtime-verify DB/Redis connectivity without the Docker stack running; verification is
  limited to import + unit-level behaviour unless the user wants live checks.

## Agent decisions

- planner: this plan (no code written).
- ui-designer: not required (no UI scope).
- database: not required (no schema changes; engine factory is app config, not DB design).
- implementer: owns all files above.
- reviewer: verify PgBouncer connect_args, engine caching, singleton behaviour, transaction
  commit/rollback, type hints, no `print`.
- security: recommended — touches secrets (JWT_SECRET_KEY, DB/Redis passwords) and the DB trust
  boundary. Run after reviewer.
- docs-writer: update this plan status to `implemented` and record what was built; no
  application-stack doc changes required (docs already describe planned shape).
- spec-writer: not required (no user-facing functionality).
- version-control: commit plan + code together at the end.

## What was built

Env strategy: **Option A (app-prefixed vars)** confirmed at approval.

- `app/infrastructure/settings.py` — `Settings(BaseSettings)` with `model_config =
  SettingsConfigDict(env_file=".env", extra="ignore")`. App-facing DB fields read from
  `APP_POSTGRES_*` env vars (`app_postgres_host` default `localhost`, `app_postgres_port` default
  `6432`, plus required user/password/db). Redis fields (`redis_host`/`redis_port` defaults,
  required `redis_password`) and JWT fields (`jwt_secret_key` required, `jwt_algorithm` default
  `HS256`, `jwt_access_token_expire_minutes` default `30`). `get_settings()` is `@lru_cache`-backed,
  returning a cached singleton.
- `app/infrastructure/database.py` — module-level `_engine_cache: dict[str, AsyncEngine]`.
  `get_engine(db_name)` lazily builds `postgresql+asyncpg://...` URL from settings, caches per
  `db_name`, uses `poolclass=NullPool` and `connect_args={"prepared_statement_cache_size": 0}` for
  PgBouncer transaction pooling. `get_session(db_name)` returns an `async_sessionmaker` bound to the
  cached engine with `expire_on_commit=False`. `get_db(db_name)` is an async-generator FastAPI
  dependency that yields an `AsyncSession` and closes it in `finally`.
- `app/infrastructure/redis.py` — module-level singleton `_pool: ConnectionPool | None`.
  `get_redis_pool()` builds the pool once from settings (`decode_responses=True`). `get_redis()` is
  an async-generator dependency yielding a `Redis` bound to the pool and closing it in `finally`.
- `app/infrastructure/transaction.py` — `TransactionHelper.wrap(session, func, *args, **kwargs)`
  awaits `func`, commits on success and returns its result, rolls back and re-raises on exception.
- `.env` — appended app-facing block (`APP_POSTGRES_HOST/PORT/USER/PASSWORD/DB`, `JWT_SECRET_KEY`)
  without modifying any existing Docker vars. `APP_POSTGRES_PASSWORD` copied from `POSTGRES_PASSWORD`.

Notes / deviations:
- `prepared_statement_name_func` was not added; only the mandatory `prepared_statement_cache_size=0`
  was set, per the implementation spec for this task.
- No re-exports added to `__init__.py` (it was the optional item); kept it empty.
- No commands run, no packages installed, no server wiring (per task constraints).

## Approval log

- 2026-05-20: plan drafted, awaiting user approval. Open question: confirm env strategy (option A
  app-prefixed vars, recommended) vs option B (repoint existing `.env` DB vars to host values).
