# Backend

The backend is an async Python service that serves all of Warehouse's API. This
document covers each part of the stack, why it was chosen, and how it is used,
followed by the layered request architecture every endpoint follows.

> Status: the infrastructure these components connect to is **implemented**; the
> application code described here is **planned** (foundation scope).

## Tech stack

### Python 3.12+

The implementation language. 3.12 is the floor for modern typing features and
performance improvements. **Type hints are required** on all function signatures
and class fields.

### FastAPI (async)

The HTTP framework. Chosen for:

- First-class `async`/`await`, which matches an I/O-bound workload (database,
  Redis, external calls).
- Automatic request validation and OpenAPI schema generation.
- Dependency injection that fits the layered architecture (services and the
  tenant DB session are injected per request).

FastAPI owns only routing and request/response handling. Business logic lives in
the service layer, not in route functions.

### SQLAlchemy (async ORM + Core)

Database access library, used in two modes:

- **ORM** for CRUD on entities — concise, mapped to `Data` classes.
- **Core** for complex queries and reporting — explicit SQL construction where the
  ORM would obscure intent or hurt performance.

All access runs through the async engine and async sessions. SQLAlchemy engines are
created **per tenant** by the dynamic engine factory (see
[`multi-tenancy.md`](./multi-tenancy.md)).

### asyncpg

The async PostgreSQL driver SQLAlchemy uses under the hood. It is the fastest
mature async driver for PostgreSQL and the natural fit for an async stack.

> Note: because the app connects through PgBouncer in **transaction** pooling
> mode, server-side prepared statement caching must be configured appropriately
> (asyncpg statement caching is disabled or named per-connection) so cached plans
> are not reused across pooled server connections.

### Alembic

Schema migration tool. Warehouse runs Alembic in a **multi-database** mode: a
single migration set is applied to the `aton_clients` registry and to every
`client_{slug}` tenant database. New tables also require updates to the seed SQL
per the project rules. See [`multi-tenancy.md`](./multi-tenancy.md#migrations-multi-db-alembic).

### JWT (stateless auth)

Authentication is stateless: tenant identity and role travel inside the signed
token. Claims are `sub`, `tenant_id`, `role`, `exp`. Verification happens in
middleware, so controllers receive an already-verified identity. `tenant_id` and
`role` are **never** read from the request body or query params. See
[`auth.md`](./auth.md).

### Redis

Used for:

- **Caching** hot reads.
- **Rate limiting** at the request boundary.
- **Refresh token storage** — refresh tokens are stored here so they can be
  revoked (logout, rotation).
- **ARQ job queue** — the broker for background jobs.

### ARQ

Async background job processor. Work that is slow or does not need to block the
response — inventory recalculation, report generation, email — is enqueued in
Redis and run by the ARQ worker out of band. The worker runs in Docker.

### PgBouncer

Connection pooler in front of PostgreSQL, running in **transaction** pooling mode
on port 6432. The async app can open many logical sessions while PgBouncer
multiplexes them onto a small set of real PostgreSQL connections. The app always
connects through PgBouncer, never directly to PostgreSQL.

### PostgreSQL (with RLS)

The primary database engine (version 16). Beyond storing all data, it provides
**Row-Level Security** as a second tenant-isolation layer underneath the
application's own `tenant_id` filtering and the database-per-tenant boundary.

## Layered architecture

Every request flows through the same fixed pipeline:

```
Controller → Request → Service → Storage → Data ↔ Database
```

```
HTTP ─▶ Controller ─▶ Request ─▶ Service ─▶ Storage ─▶ Database
          │            (validate) (logic)   (SQL)        │
          │                                  │           │
          └───────────────  Data  ◀──────────┴───────────┘
                          (entity shape)
```

| Layer | Responsibility |
|---|---|
| Controller | Route requests, return responses, wrap mutations in `TransactionHelper`. |
| Request | Validate and normalize all input at the boundary. |
| Service | All business logic; coordinates storages. |
| Storage | All database access; returns `Data` / `DataCollection` / `None`. |
| Data | Entity shape, `from_row` factory, no logic. |
| Error | `ApplicationError` subclasses with unique error codes. |

### Layer rules

**Controller**
- No business logic.
- No direct database access.
- Lazy-resolve services on demand.
- Wrap all mutations using `transaction_helper.wrap(db, ...)`.

**Request**
- All validation happens here, never in services.
- PATCH requests validate only submitted fields using `model_fields_set`.
- Validated input is trusted downstream — it is not re-validated.
- Implemented as typed classes that validate at the boundary.

**Service**
- All business logic lives here.
- Never starts transactions.
- Never accesses the database directly.
- Uses storages for all reads and writes.

**Storage**
- The only layer that touches the database.
- Never starts transactions.
- Assigns generated primary keys back onto the `Data` object it was given.
- Returns `Data`, `DataCollection`, or `None` — nothing else.
- **Filters every query by `tenant_id`** — no exceptions.

**Data**
- One class per entity, implemented as a `dataclass`.
- Field names match DB column names exactly.
- `from_row` is a `@classmethod` factory.
- No business logic or methods beyond `__init__` and `from_row`.

**Error**
- Extends `ApplicationError`.
- Uses `ErrorDefinitions` for message text.
- Error codes are unique across the system.

### Transactions

- The **controller** wraps mutations in a transaction (`transaction_helper.wrap`).
- The **service** never starts a transaction.
- The **storage** operates within the transaction the controller opened.

## Naming conventions

| Item | Convention |
|---|---|
| Files | `snake_case.py` |
| Classes | `PascalCase` |
| Functions / methods | `snake_case` |
| Constants | `UPPER_SNAKE_CASE` |

Type hints are required on all signatures and fields.

## Folder structure

```
app/
  controllers/{domain}/
  requests/{domain}/
  services/{domain}/
  storages/
  data/
  errors/{domain}/
  helpers/
  infrastructure/
main.py
```

## Anti-patterns (do not do)

- Manager / Repository pattern — use **Storage**.
- Service Locator — use constructor or dependency injection.
- Facade / hidden layers — keep every layer explicit in the folder structure.
- DI inside abstract classes — keep abstract classes pure.
- Business logic in controllers.
- Database access outside storages.
- Speculative optimization (index only documented access patterns).
- Using `dict` as an entity when a `Data` class exists.
- `print()` for logging — use the `logging` module.
- Missing type hints.
- Mutable default arguments (`def f(x=[])`).
