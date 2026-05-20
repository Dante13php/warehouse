# Multi-Tenancy

Warehouse isolates tenants with a **database-per-tenant** strategy. Every tenant
(client) gets its own PostgreSQL database; a central registry maps tenants to
their databases; each request is routed to the correct database based on the
caller's verified JWT claims.

> Status: the `aton_clients` registry database is created by the Docker init
> script (**implemented**). The router, engine factory, and multi-DB Alembic
> runner are **planned** (foundation scope).

## Why database-per-tenant

- **Strong isolation.** A tenant's data lives in a physically separate database,
  so a query bug cannot leak across tenants the way a missing `WHERE tenant_id`
  could in a shared-schema model.
- **Independent scaling and maintenance.** Tenant databases can be backed up,
  restored, or moved individually.
- **Defense in depth.** Application-level `tenant_id` filtering and PostgreSQL RLS
  sit on top of the per-database boundary, giving three layers of protection.

## Topology

```
                        ┌──────────────────────────────┐
                        │        PostgreSQL 16          │
                        │                                │
   request (JWT) ──┐    │  ┌──────────────┐              │
                   │    │  │ aton_clients │  registry    │
                   │    │  │  - tenants    │             │
                   │    │  │  - slug → db  │             │
                   ▼    │  └──────────────┘              │
            ┌──────────┐│  ┌──────────────┐              │
            │ DB router ├──▶│ client_acme  │  tenant A    │
            │ (tenant_  ││  └──────────────┘             │
            │  id)      ││  ┌──────────────┐             │
            └──────────┘│  │ client_globex│  tenant B    │
                        │  └──────────────┘              │
                        │  ┌──────────────┐              │
                        │  │ client_{slug}│  tenant N …  │
                        │  └──────────────┘              │
                        └────────────────────────────────┘
```

## The `aton_clients` registry

`aton_clients` is the central control database. It holds the list of tenants and
the metadata needed to reach each tenant's database — at minimum the tenant id,
the client `slug`, and the target database name (`client_{slug}`). It may also
hold provisioning state and tenant-level configuration.

It is created on first PostgreSQL startup by
[`docker/init-db.sql`](../../docker/init-db.sql), which guarantees the database
exists before any migration runs. RLS, tenant tables, and the full schema are
applied afterward by Alembic — the init script only bootstraps the database.

## Per-tenant databases (`client_{slug}`)

Each tenant has a dedicated database named `client_{slug}`, where `slug` is the
tenant's registry identifier. Every tenant database carries the same application
schema (warehouses, inventory, production, sales, users, etc.). All tenant tables
include a `tenant_id` column and have RLS enabled, even though the database is
already tenant-private — this is the deliberate defense-in-depth posture.

Onboarding a new tenant means: insert a registry row in `aton_clients`, create
the `client_{slug}` database, and run migrations + seed against it.

## Request routing

Tenant selection is driven entirely by the **verified** JWT, never by user input.

1. Auth middleware verifies the token and produces a trusted identity containing
   `tenant_id` (see [`auth.md`](./auth.md)).
2. The database router takes `tenant_id`, looks up (or has cached) the tenant's
   target database, and obtains the matching SQLAlchemy engine from the engine
   factory.
3. A request-scoped async session bound to that engine is injected into the
   layers. Every storage query then runs against the correct tenant database.

```
JWT claims ──▶ auth middleware ──▶ identity{ tenant_id }
                                       │
                                       ▼
                              ┌────────────────┐
                              │  DB router     │  resolve tenant → db name
                              └───────┬────────┘
                                      ▼
                              ┌────────────────┐
                              │ engine factory │  get/create engine for db
                              └───────┬────────┘
                                      ▼
                              async session  ──▶ Storage layer
```

Because `tenant_id` comes from a signed claim, a caller cannot point themselves at
another tenant's database by tampering with request parameters.

## Dynamic SQLAlchemy engine factory

There is no single static engine. Instead a factory produces one async engine per
tenant database on demand:

- **Lazy creation.** The first request for a tenant creates that tenant's engine;
  subsequent requests reuse it.
- **Caching.** Engines are cached (keyed by tenant / database name) so connection
  pools are not rebuilt per request.
- **Pooling through PgBouncer.** Every engine's DSN points at PgBouncer (port
  6432), not directly at PostgreSQL. Because PgBouncer runs in transaction pooling
  mode, the engines are configured accordingly (e.g. disable SQLAlchemy's own
  pooling / use a null-style pool and disable prepared-statement caching) so the
  two poolers do not fight.

Conceptually:

```python
# Planned shape — illustrative, not final code.
class EngineFactory:
    def __init__(self) -> None:
        self._engines: dict[str, AsyncEngine] = {}

    def get_engine(self, db_name: str) -> AsyncEngine:
        engine = self._engines.get(db_name)
        if engine is None:
            engine = create_async_engine(self._dsn_for(db_name))  # via PgBouncer
            self._engines[db_name] = engine
        return engine
```

A separate registry engine targets `aton_clients` for tenant lookups and
provisioning.

## Migrations: multi-DB Alembic

A single migration history must be applied to many databases. Warehouse uses a
**multi-DB Alembic runner** that:

1. Reads the tenant list from the `aton_clients` registry.
2. Applies migrations to the registry database itself.
3. Iterates over every `client_{slug}` database and applies the same migration
   set to each.

This keeps all tenant schemas in lockstep. Per the project rules, new tables also
require corresponding updates to the seed SQL (`warehouse_full_seed.sql`) so a
freshly provisioned tenant database starts with the expected schema and seed data.

Provisioning a new tenant therefore reuses the same migration path the runner uses
for existing tenants.

## RLS as a second layer

Even with a private database per tenant and application-level `tenant_id`
filtering on every storage query, PostgreSQL Row-Level Security is enabled on
tenant tables. RLS is the backstop: if application code ever forgets a tenant
filter, the database still refuses rows outside the active tenant context.
Cross-tenant access is only possible through an explicit admin context, never
through a normal service call.

## Rules recap

- Every table has a `tenant_id` column.
- Every storage query filters by `tenant_id` — no exceptions.
- `tenant_id` is resolved from JWT claims at the request boundary and passed
  through the service and storage layers; it is never derived from user input.
- RLS is enabled as a second enforcement layer.
- Cross-tenant data access requires an explicit admin context.
