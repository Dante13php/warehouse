# Architecture Overview

## What Warehouse is

Warehouse is a multi-tenant warehouse and inventory management system. Each tenant
(client) is an isolated business with its own warehouses, stock, production
processes, sales, and staff. The system covers four business areas:

- **Warehouses** — multiple physical locations and their stock levels.
- **Production** — manufacturing that consumes raw materials and produces finished goods.
- **Sales** — sales orders and customer-facing transactions.
- **Inventory** — stock tracking, counts, adjustments, and movements between locations.

The design priorities are scalability, performance, and user experience.

## High-level shape

The platform is a backend API plus its supporting infrastructure. A FastAPI
application serves all HTTP traffic. It authenticates callers with JWTs, resolves
which tenant the caller belongs to, routes the request to that tenant's own
database, and runs the business logic. Heavy or slow work (inventory recalculation,
reports, email) is handed off to an async background worker.

```
                         ┌──────────────────────────┐
        HTTP / JWT       │      FastAPI app          │
   client ───────────▶   │  (runs locally in dev)    │
                         │                            │
                         │  auth middleware           │
                         │  tenant DB router          │
                         │  Controller→…→Storage      │
                         └───┬───────────┬────────┬───┘
                             │           │        │
              DB access via  │           │ cache, │ enqueue
              PgBouncer      │           │ tokens,│ jobs
                             ▼           ▼        ▼
                    ┌──────────────┐  ┌───────┐  (job queue
                    │  PgBouncer   │  │ Redis │   in Redis)
                    │ :6432 pooler │  └───┬───┘
                    └──────┬───────┘      │
                           │              │ pops jobs
                           ▼              ▼
                    ┌──────────────┐  ┌────────────┐
                    │ PostgreSQL16 │  │ ARQ worker │
                    │  aton_clients│  │  (async)   │
                    │  client_*    │  └────────────┘
                    │  + RLS       │
                    └──────────────┘
```

## Core components

| Component | Role |
|---|---|
| **FastAPI app** | Async HTTP API. Routing, auth, tenant routing, business logic. Runs locally during development, outside Docker. |
| **PostgreSQL 16** | Primary datastore. Holds the `aton_clients` registry plus one `client_{slug}` database per tenant. Row-Level Security (RLS) is a second isolation layer. |
| **PgBouncer** | Connection pooler in front of PostgreSQL (transaction pooling, port 6432). Lets the async app open many logical connections without exhausting PostgreSQL. |
| **Redis 7** | Caching, rate limiting, revocable refresh-token storage, and the ARQ job queue. |
| **ARQ worker** | Async background job processor. Runs slow/deferred work off the request path. |

## How a request flows

1. A client sends an HTTP request with a JWT in the `Authorization` header.
2. Auth middleware verifies the token signature and expiry and builds a trusted
   identity object from the claims (`sub`, `tenant_id`, `role`, `exp`).
3. The tenant database router uses `tenant_id` to select the correct per-tenant
   engine (created on demand by the dynamic engine factory).
4. The request passes through the application layers:
   `Controller → Request → Service → Storage → Data ↔ Database`.
5. Reads and writes go through PgBouncer to the tenant's PostgreSQL database; RLS
   enforces tenant scoping as a backstop.
6. If the work is slow or deferrable, the service enqueues an ARQ job in Redis;
   the worker picks it up and runs it asynchronously.
7. The controller returns a response. All mutations are wrapped in a transaction
   at the controller layer.

## Application layers

Every request travels through a fixed set of layers, each with one
responsibility. This keeps business logic, validation, and database access cleanly
separated.

```
Controller → Request → Service → Storage → Data ↔ Database
```

| Layer | Responsibility |
|---|---|
| Controller | Route requests, return responses, wrap mutations in a transaction. No business logic, no direct DB access. |
| Request | Validate and normalize all input at the boundary. |
| Service | All business logic. Coordinates storages. Never starts transactions or touches the DB directly. |
| Storage | The only layer that touches the database. Filters every query by `tenant_id`. |
| Data | Plain entity shape (`dataclass`) with a `from_row` factory. No logic. |
| Error | `ApplicationError` subclasses with unique error codes. |

See [`backend.md`](./backend.md) for the detailed layer rules.

## Multi-tenancy at a glance

Warehouse uses **database-per-tenant** isolation:

- A central `aton_clients` database is the client registry — it maps each tenant
  to its dedicated database.
- Each tenant gets its own `client_{slug}` database with the full application
  schema.
- The active database is chosen per request from the JWT's `tenant_id` claim,
  never from user input.
- A dynamic SQLAlchemy engine factory creates and caches one engine per tenant.
- A multi-DB Alembic runner applies migrations across the registry and every
  tenant database.

Details are in [`multi-tenancy.md`](./multi-tenancy.md).

## Authentication at a glance

- Stateless, short-lived JWT access tokens (15–60 minutes).
- Revocable refresh tokens stored in Redis.
- Token claims carry `sub` (user id), `tenant_id`, `role`, and `exp`.
- Roles are `manager` and `staff`; passwords are hashed with bcrypt.
- Endpoints: `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`.

Details are in [`auth.md`](./auth.md).

## Where things run

- **Infrastructure** (PostgreSQL, PgBouncer, Redis, ARQ worker) runs in Docker via
  Docker Compose. This part is **implemented**.
- **The FastAPI application** runs locally during development and connects to the
  Dockerized services over published ports. The application code itself is
  **planned**.

See [`infrastructure.md`](./infrastructure.md) for the runtime topology and setup.
