# Application Stack Documentation

This folder documents the **planned technical architecture** of Warehouse — the
full intended tech stack and how the application is designed to work, not only
what is implemented so far.

Warehouse is a multi-tenant warehouse and inventory management system. It tracks
stock across multiple warehouse locations, records stock movements and inventory
levels, drives production processes, and controls staff access.

## Contents

| File | Scope |
|---|---|
| [`overview.md`](./overview.md) | High-level architecture: what Warehouse is, the main components, and how they connect. |
| [`backend.md`](./backend.md) | Backend tech stack in detail: each component, why it was chosen, how it is used, and the layered request flow. |
| [`multi-tenancy.md`](./multi-tenancy.md) | Database-per-tenant strategy: the client registry, per-tenant databases, request routing, the dynamic engine factory, and multi-DB Alembic. |
| [`auth.md`](./auth.md) | Authentication: JWT access tokens, Redis-backed refresh tokens, the login / refresh / logout flows, middleware, and token claims. |
| [`infrastructure.md`](./infrastructure.md) | Docker services (PostgreSQL, PgBouncer, Redis, ARQ worker), how the local FastAPI app connects to them, connection strings, and local dev setup. |

## How to read this

Start with [`overview.md`](./overview.md) for the big picture. Then dive into the
area you care about:

- Building or extending API features → [`backend.md`](./backend.md)
- Working with tenant isolation or onboarding clients → [`multi-tenancy.md`](./multi-tenancy.md)
- Touching login, sessions, or permissions → [`auth.md`](./auth.md)
- Running the stack locally or changing services → [`infrastructure.md`](./infrastructure.md)

## Status legend

Throughout these docs, components are marked to distinguish what exists today from
what is planned:

- **Implemented** — present in the repository now (e.g. the Docker Compose stack).
- **Planned** — part of the foundation scope, not yet written.

## Source of truth

These documents describe architecture and intent. The authoritative coding and
architecture rules live in [`.claude/rules/RULES.md`](../../.claude/rules/RULES.md);
product context lives in [`CLAUDE.md`](../../CLAUDE.md). Where this documentation
and the rules disagree, the rules win.
