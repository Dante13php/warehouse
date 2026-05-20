# Python Project Skeleton

## Status

`implemented`

## Source task

User request: create the folder skeleton of the Warehouse Python project — the layered `app/` structure, a minimal FastAPI `main.py`, and a uv-compatible `pyproject.toml` with the foundation-scope dependencies.

## Scope

Create the backend Python skeleton that matches the layered architecture defined in `.claude/rules/RULES.md`:

```
app/
  controllers/
  requests/
  services/
  storages/
  data/
  errors/
  helpers/
  infrastructure/
main.py
pyproject.toml
```

- `__init__.py` in `app/` and in every subpackage so each layer is an importable package.
- `main.py` — a minimal FastAPI application: only the `FastAPI()` instance, no routes, no middleware, no DB wiring.
- `pyproject.toml` — uv-compatible (PEP 621 `[project]` table), Python `>=3.12`, declaring the foundation dependencies listed below.

### Foundation dependencies

`fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `redis[hiredis]`, `python-jose[cryptography]`, `passlib[bcrypt]`, `arq`, `pydantic`, `pydantic-settings`.

## Out of scope

- Any controller / request / service / storage / data / error implementation code (packages are created empty except `__init__.py`).
- Routes, middleware, dependency injection, settings classes, DB engine factory, Redis client.
- Alembic environment / migration scaffolding (`alembic init`).
- Pinning exact dependency versions beyond a minimum floor and Python `>=3.12`.
- `.env` parsing, Docker changes, CI configuration, tests.
- Lockfile generation (`uv.lock`).

## Acceptance criteria

- The directory tree above exists exactly as specified.
- `app/` and all eight subpackages contain an `__init__.py`.
- `main.py` defines a module-level `app = FastAPI(...)` and nothing else of substance.
- `pyproject.toml` is valid PEP 621, sets `requires-python = ">=3.12"`, and lists all eleven foundation dependencies with their extras exactly as written.
- `uvicorn app.main:app` would be the documented run target (no route is required to exist).
- No business logic, no DB access, no hardcoded credentials anywhere in the created files.

## Impacted files

| File | Action |
|---|---|
| `pyproject.toml` | created |
| `app/__init__.py` | created |
| `app/main.py` | created |
| `app/controllers/__init__.py` | created |
| `app/requests/__init__.py` | created |
| `app/services/__init__.py` | created |
| `app/storages/__init__.py` | created |
| `app/data/__init__.py` | created |
| `app/errors/__init__.py` | created |
| `app/helpers/__init__.py` | created |
| `app/infrastructure/__init__.py` | created |

> Note: the task description shows `main.py` at repo root, but RULES.md folder structure places `main.py` inside `app/`. The plan follows RULES.md (`app/main.py`) so the run target is `app.main:app`. This is the one deviation from the literal task layout and is called out for approval.

## Risks

- `python-jose` and `passlib` are effectively unmaintained; acceptable for the foundation scope since they are explicitly requested, but flagged for a future security review.
- No version pinning means `uv` resolves latest at install time; reproducibility depends on a later `uv.lock`, which is out of scope here.
- Empty packages with only `__init__.py` will show as effectively empty in some tooling; intentional for a skeleton.

## Agent decisions

- planner: this plan (orchestrator-internal planning; no code written during planning).
- ui-designer: not required (no UI scope).
- database: not required (no schema changes).
- implementer: owns creation of all files listed above.
- reviewer: verify tree, `__init__.py` presence, `pyproject.toml` validity, and that `main.py` contains only the app instance.
- security: not required for this scope (no auth/secrets/trust-boundary code), but `python-jose`/`passlib` flagged above for when auth is implemented.
- docs-writer: update this plan status to `implemented` after build.
- version-control: not requested by the user; do not commit unless asked.

## Approval log

- 2026-05-20: drafted, pending user approval.

## What was built

Created on 2026-05-20:

- `pyproject.toml` — PEP 621 / uv-compatible, `requires-python = ">=3.12"`, all eleven foundation dependencies with extras (no version pins).
- `app/main.py` — minimal FastAPI instance: `app = FastAPI(title="Warehouse")`.
- `app/__init__.py` plus empty `__init__.py` in all eight layer subpackages: `controllers`, `requests`, `services`, `storages`, `data`, `errors`, `helpers`, `infrastructure`.

Run target: `uvicorn app.main:app`.
