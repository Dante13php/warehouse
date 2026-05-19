# Warehouse

Warehouse is a warehouse and inventory management system. It manages multiple warehouse locations, tracks stock movements and inventory levels, handles production processes, and controls staff access.
Always aim for scalability and performance. As well as maximum UX.

## Entry Point

For every task:

- **Question-only** (no code, no doc changes): answer directly without spawning agents.
- **All other tasks**: spawn an `Agent` tool call with:
  - `description`: `"Orchestrator: <кратко описание на задачата>"`
  - `model`: `"opus"`
  - `prompt`: съдържанието на `.claude/agents/orchestrator.md` + задачата на потребителя

Никога не изпълнявай implementation работа директно — делегирай на orchestrator агента.

## Infrastructure

All infrastructure services run in Docker. The local development environment uses Docker Compose to orchestrate:

- **PostgreSQL** — primary database with RLS enabled
- **PgBouncer** — connection pooler in front of PostgreSQL
- **Redis** — caching, rate limiting, refresh token storage, ARQ job queue
- **ARQ worker** — async background job processor

The FastAPI application itself runs locally (outside Docker) during development and connects to the Dockerized services. Never hardcode connection strings — all service URLs and credentials are supplied via environment variables.

## Key References

- `.claude/agents/` — agent definitions
- `.claude/rules/RULES.md` — architecture and coding rules
- `docs/api/ENDPOINTS.md` — API contracts
- `docs/product/` — domain glossary, business rules, product overview
- `docs/plans/` — implementation plans
