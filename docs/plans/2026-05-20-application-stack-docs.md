# Application Stack Documentation

## Status

`implemented`

## Source task

User request: write technical documentation describing the full planned tech stack and how the application works, stored in `docs/application-stack/`.

## Scope

Create a `docs/application-stack/` subfolder with six markdown files covering the full planned architecture of Warehouse — not just what is currently implemented.

## Out of scope

- Application code
- API endpoint reference (`docs/api/`)
- Domain glossary or business rules
- Frontend documentation

## Acceptance criteria

- `docs/application-stack/README.md` exists with folder index
- Each major architectural concern has its own file
- Diagrams (ASCII or Mermaid) illustrate non-obvious relationships
- Content accurately reflects both implemented infrastructure and planned application code
- No credentials or secrets appear in documentation

## Impacted files

| File | Action |
|---|---|
| `docs/application-stack/README.md` | created |
| `docs/application-stack/overview.md` | created |
| `docs/application-stack/backend.md` | created |
| `docs/application-stack/multi-tenancy.md` | created |
| `docs/application-stack/auth.md` | created |
| `docs/application-stack/infrastructure.md` | created |

## Risks

- Documentation describes planned behavior — sections covering application code (auth, multi-tenancy routing, engine factory) describe design intent, not implemented code
- Must be kept in sync as implementation progresses

## Agent decisions

- planner: skipped (docs-only task treated as direct)
- docs-writer: executed directly by orchestrator agent
- reviewer: not run

## Approval log

- 2026-05-20: implemented directly without prior plan approval (retroactive)

## What was built

- `README.md` — index table with file descriptions and implemented/planned status legend
- `overview.md` — high-level architecture, four business areas (Warehouses, Production, Sales, Inventory), ASCII topology diagram, request flow, application layers summary
- `backend.md` — full tech stack with rationale per component, layer rules, transactions, naming conventions, folder structure, anti-patterns
- `multi-tenancy.md` — database-per-tenant strategy, `aton_clients` registry, `client_{slug}` databases, JWT-driven routing, dynamic engine factory, multi-DB Alembic runner, RLS as defense-in-depth
- `auth.md` — JWT claims, users/roles, bcrypt, three auth endpoints, ASCII sequence diagrams for login/refresh/logout flows
- `infrastructure.md` — Docker services table, network topology, per-service detail, env-var reference, local dev setup steps
