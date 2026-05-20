# Infrastructure

All supporting services run in Docker, orchestrated by Docker Compose. The FastAPI
application runs **locally** during development (outside Docker) and connects to
the Dockerized services over published host ports.

> Status: the Docker Compose stack described here is **implemented**. The FastAPI
> app that connects to it is **planned**.

## Services

| Service | Image | Container | In-network port | Published port |
|---|---|---|---|---|
| PostgreSQL | `postgres:16-alpine` | `warehouse-postgres` | 5432 | `POSTGRES_PUBLISHED_PORT` (5432) |
| PgBouncer | `edoburu/pgbouncer:latest` | `warehouse-pgbouncer` | 6432 | `PGBOUNCER_PUBLISHED_PORT` (6432) |
| Redis | `redis:7-alpine` | `warehouse-redis` | 6379 | `REDIS_PUBLISHED_PORT` (6379) |
| ARQ worker | built from `docker/arq/Dockerfile` | `warehouse-arq-worker` | — | — |

All services join a single user-defined bridge network named `warehouse`, so they
reach each other by container/service name (e.g. `postgres`, `redis`). Each has a
healthcheck; PgBouncer and the ARQ worker wait for their dependencies to be
healthy before starting.

```
                          host (localhost)
   ┌──────────────────────────────────────────────────────────┐
   │  FastAPI app (local dev)                                   │
   │     │ DB  → localhost:6432            │ Redis → localhost:6379
   └─────┼──────────────────────────────────┼──────────────────┘
         │                                   │
   ══════╪═══════════════ docker network "warehouse" ═══════════╪═════
         ▼                                   ▼
   ┌────────────┐  postgres:5432   ┌──────────────┐    ┌────────────┐
   │ pgbouncer  │ ───────────────▶ │ postgres:16  │    │  redis:7   │
   │  :6432     │                  │  aton_clients │    │  :6379     │
   └────────────┘                  │  client_*     │    └─────┬──────┘
                                   └──────────────┘          │ job queue
                                                       ┌──────▼──────┐
                                                       │ arq-worker  │
                                                       └─────────────┘
```

### PostgreSQL

- Version 16 (alpine). The primary datastore.
- On first start (empty data dir) it runs
  [`docker/init-db.sql`](../../docker/init-db.sql), which guarantees the
  `aton_clients` registry database exists. RLS, tenant tables, and the full schema
  are added later by Alembic — the init script only bootstraps.
- Data persists in the named volume `warehouse_postgres_data`.
- Exposed on the host (default 5432) for direct access and debugging. **The
  application does not connect here directly** — it goes through PgBouncer.

### PgBouncer

- Connection pooler in front of PostgreSQL, configured by
  [`docker/pgbouncer/pgbouncer.ini`](../../docker/pgbouncer/pgbouncer.ini).
- **Transaction pooling** mode: a server connection is held only for the duration
  of a transaction, which is what lets the async app sustain high concurrency
  without exhausting PostgreSQL connections.
- Defaults: `max_client_conn = 200`, `default_pool_size = 25` (overridable via
  env).
- Auth is `md5` against
  [`docker/pgbouncer/userlist.txt`](../../docker/pgbouncer/userlist.txt).
- Listens on 6432; the app connects here for all database access.

> Because pooling is per-transaction, server connections are shared across
> clients. The application's SQLAlchemy engines must be configured to suit this
> (no reliance on session-level state across transactions; prepared-statement
> caching handled appropriately for asyncpg). See
> [`multi-tenancy.md`](./multi-tenancy.md#dynamic-sqlalchemy-engine-factory).

### Redis

- Version 7 (alpine). Backs caching, rate limiting, refresh-token storage, and the
  ARQ job queue.
- Started with a password (`--requirepass`) and append-only persistence
  (`--appendonly yes`).
- Data persists in the named volume `warehouse_redis_data`.
- Exposed on the host (default 6379) so the locally-run app can reach it.

### ARQ worker

- Built from [`docker/arq/Dockerfile`](../../docker/arq/Dockerfile) (Python 3.12
  slim + `arq` + `redis`).
- Connects to Redis via `ARQ_REDIS_URL` and processes background jobs.
- Currently a **placeholder** image that stays alive until the real worker module
  lands. When the app code exists, the entrypoint becomes:
  `arq app.infrastructure.worker.WorkerSettings`.

## Configuration and connection strings

All service URLs and credentials come from environment variables in a local
`.env` file (copied from the committed example template). **Nothing is
hardcoded**, and the real `.env` is never committed.

Key variables:

| Variable | Used by | Purpose |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | PostgreSQL, PgBouncer | Primary DB credentials and default database. |
| `POSTGRES_PUBLISHED_PORT` | host | Host port PostgreSQL is exposed on. |
| `PGBOUNCER_PUBLISHED_PORT` | host / app | Host port PgBouncer is exposed on (the app connects here). |
| `PGBOUNCER_POOL_MODE` | PgBouncer | `transaction` (default). |
| `PGBOUNCER_MAX_CLIENT_CONN` / `PGBOUNCER_DEFAULT_POOL_SIZE` | PgBouncer | Pool sizing. |
| `PGBOUNCER_AUTH_HASH` | PgBouncer | md5 hash matching `userlist.txt`. |
| `REDIS_PASSWORD` | Redis, app, worker | Redis auth. |
| `REDIS_PUBLISHED_PORT` | host / app | Host port Redis is exposed on. |
| `ARQ_REDIS_URL` | ARQ worker | Redis DSN for the job queue. |

### What the local app uses

The FastAPI app runs on the host, so it targets `localhost` and the **published**
ports — not the in-network service names:

```
# Database — through PgBouncer, per tenant database name resolved at runtime:
postgresql+asyncpg://<user>:<password>@localhost:6432/<db_name>

# Redis:
redis://:<password>@localhost:6379/0
```

Containers talking to each other use service names instead (e.g. PgBouncer →
`postgres:5432`, the worker → `redis://...@redis:6379/0`).

## Local development setup

1. **Copy the env template** and fill in real values:

   ```bash
   cp .env.example .env
   ```

   Replace placeholder credentials. To regenerate the PgBouncer md5 hash for the
   PostgreSQL user:

   ```bash
   echo -n "md5$(echo -n '<password><user>' | md5sum | cut -d' ' -f1)"
   ```

   Put the result in both `PGBOUNCER_AUTH_HASH` and
   `docker/pgbouncer/userlist.txt`.

2. **Start the infrastructure:**

   ```bash
   docker compose up -d
   ```

   Compose brings up PostgreSQL first, then PgBouncer and the ARQ worker once
   their dependencies are healthy.

3. **Verify health:**

   ```bash
   docker compose ps
   ```

   All services should report healthy. PostgreSQL's first start runs
   `init-db.sql` to ensure `aton_clients` exists.

4. **Run the FastAPI app locally**, pointing it at `localhost:6432` (database) and
   `localhost:6379` (Redis) using the values from `.env`. (Application code is
   planned; this step applies once it exists.)

5. **Apply migrations** with the multi-DB Alembic runner to bring the registry and
   all tenant databases up to the current schema (see
   [`multi-tenancy.md`](./multi-tenancy.md#migrations-multi-db-alembic)).

## Why this topology

- **Infra in Docker, app on the host** gives a reproducible, disposable set of
  backing services while keeping the application fast to iterate on locally
  (instant reload, native debugging).
- **PgBouncer in front of PostgreSQL** is essential for an async app that opens
  many connections; transaction pooling keeps real PostgreSQL connections scarce
  and reusable.
- **Redis as one service for cache, tokens, rate limiting, and the queue** keeps
  the moving parts minimal while covering several cross-cutting needs.
- **A separate ARQ worker** keeps slow work off the request path without blocking
  API responses.
