# Users Controller — CRUD method naming + path-parameter subfolder conventions

## Status

`implemented` — controller-only refactor executed 2026-05-21 (planner → implementer →
reviewer → docs-writer → version-control). See "What was built" below.

## Source task

Refactor the Users controller to follow two structural conventions:

1. **Subfolder per path parameter** — controller methods that operate on a specific
   resource by path parameter (`user_id`) live in their own subfolder named after the
   parameter, with a file of the same name inside.
2. **CRUD method names** — controller method (and thin route function) names must be exactly
   the CRUD verbs: `get` (list collection AND get one by id), `create`, `update`, `delete`.

## State at task start (verified against current source)

Convention 1 (subfolder per path parameter) was **already satisfied** by the prior
"users-endpoint" build:

- `app/controllers/users/users.py` — collection-level routes only (`GET /users`,
  `POST /users`).
- `app/controllers/users/user_id/user_id.py` — single-resource routes only
  (`GET`/`PATCH`/`DELETE /users/{user_id}`), with `app/controllers/users/user_id/__init__.py`.
- `app/main.py` — already imports and registers BOTH routers (`users_router`,
  `users_user_id_router`).

Convention 2 (CRUD method names) was **partially satisfied**. The deltas were the
controller-class methods and their thin route functions:

| File | Method (was) | Method (must be) |
|---|---|---|
| `users.py` controller method | `index` | `get` |
| `users.py` route function | `index` | `get` |
| `users.py` | `create` | `create` (unchanged) |
| `user_id/user_id.py` controller method | `read` | `get` |
| `user_id/user_id.py` route function | `read` | `get` |
| `user_id/user_id.py` | `update` | `update` (unchanged) |
| `user_id/user_id.py` | `delete` | `delete` (unchanged) |

## Scope

- Rename `UsersController.index` → `get` and its `@router.get("")` route function `index`
  → `get`.
- Rename `UserIdController.read` → `get` and its `@router.get("/{user_id}")` route function
  `read` → `get`.
- No behavior changes: same HTTP methods, same paths, same status codes, same request/
  response shapes, same auth gate, same service calls.

## Out of scope (per task)

- Service layer (`UserService.list_users`/`create_user`/`get_user`/`update_user`/
  `delete_user`) — names unchanged; the controller keeps calling the existing service
  methods. The task's "current method names" list refers to service methods, which the
  scope explicitly excludes ("No changes to any other layer").
- Storages, data, requests, errors, mappers — untouched.
- `app/main.py` router registration — already correct; no change.
- The structural split itself — already done before this task.

## Acceptance criteria

- `UsersController` exposes `get` and `create` (no `index`).
- `UserIdController` exposes `get`, `update`, `delete` (no `read`).
- Both `@router.get(...)` route functions are named `get`; collection and single-resource
  GET decorators bind to those.
- Same routes registered: `GET /users`, `POST /users`, `GET /users/{user_id}`,
  `PATCH /users/{user_id}`, `DELETE /users/{user_id}`; same status codes (201 on create,
  204 on delete).
- `python -c "import app.main"` imports cleanly with all five routes registered.

## Impacted files

| File | Action | Owner |
|---|---|---|
| `app/controllers/users/users.py` | rename `index` → `get` (method + route fn) | implementer |
| `app/controllers/users/user_id/user_id.py` | rename `read` → `get` (method + route fn) | implementer |
| `docs/api/ENDPOINTS.md` | refresh if it references controller method names | docs-writer |
| `docs/plans/2026-05-21-users-controller-crud-naming.md` | this plan; status maintained | docs-writer |

## Risks

- **Route-function name collision across modules.** Two route functions named `get` exist
  in two separate modules (`users.py`, `user_id.py`). They are module-scoped Python names,
  so no collision; FastAPI derives `operation_id` from `module.function`, so OpenAPI
  `operationId`s differ by module path. No runtime impact. Low risk.
- **`docs/api/ENDPOINTS.md` drift** — if it names controller methods, docs-writer refreshes.

## Validation notes

- `python -c "import app.main"` after the rename (both routers + all five routes register).
- Confirm route paths/verbs/status codes unchanged.

## What was built (2026-05-21)

- `app/controllers/users/users.py` — `UsersController.index` renamed to `get`; the
  `@router.get("")` route function renamed `index` → `get`; comment updated to describe
  the collection `get`. `create` unchanged.
- `app/controllers/users/user_id/user_id.py` — `UserIdController.read` renamed to `get`;
  the `@router.get("/{user_id}")` route function renamed `read` → `get`. `update`/`delete`
  unchanged. Service calls (`self.UserService.get_user(...)` etc.) left intact per scope.
- No other layers touched. `app/main.py` router registration was already correct and
  unchanged. Both conventions now hold; behavior is identical (same routes, verbs, status
  codes, auth gate, response shapes).
- Verification: `python -c "import app.main"` succeeds; the five expected routes register
  with unchanged paths and status codes.
