# Users Endpoint (users table, real UserStorage, UserService, /users CRUD)

## Status

`implemented` — all open questions (Q1–Q13) resolved by the user on 2026-05-21 and the
full workflow (database → implementer → reviewer → security → docs-writer →
version-control) executed. See "Resolved decisions (2026-05-21)", the "Open questions"
section (every question marked RESOLVED), and "What was built (2026-05-21)" below.

## What was built (2026-05-21)

Endpoint set (exactly 5 CRUD routes, no `/users/me`; authentication-only, no role gate):
`GET /users`, `POST /users`, `GET /users/{user_id}`, `PATCH /users/{user_id}`,
`DELETE /users/{user_id}`.

Database:
- `alembic/versions/client_template/20260521_0000_0001_create_users_table.py` — first
  `client_template` revision (`down_revision = None`): `user_role` enum (`manager`/`staff`),
  `users` table with `id BIGINT GENERATED ALWAYS AS IDENTITY` PK (Q3), `tenant_id UUID`,
  `email TEXT`, `password_hash TEXT`, `role user_role`, `created_at`/`updated_at TIMESTAMPTZ`,
  `UNIQUE (tenant_id, email)` (Q4), RLS enabled + forced with the `tenant_isolation` policy
  keyed off `app.tenant_id` GUC, shipped permissive-until-GUC-wired (Q5). Symmetric
  `downgrade()`.
- `warehouse_full_seed.sql` — reference schema + guarded dev-only seed (Q6).

Application:
- `app/data/user_data.py` — `UserData(AbstractData)` (integer `id`), `to_response()` omits
  `password_hash` and emits ISO-8601 `Z` (Q10).
- `app/storages/user_storage.py` — real `UserStorage` (`get_by_email`, `get_by_id`, `list`,
  `create`, `update`, `delete`); every authenticated query `tenant_id`-scoped; SQLAlchemy
  Core `text()`; `create` assigns generated id/timestamps back.
- `app/services/users/user_service.py` — `UserService`: list/get/create/update/delete; no
  role gate (Q7); self-delete guard (Q12); duplicate-email checks; bcrypt hashing.
- `app/requests/users/create_user_request.py`, `update_user_request.py` — email normalize
  + numeric-PIN (6–14 digits) validation (Q9); PATCH validates only submitted fields.
- `app/controllers/users/users.py` — `UsersController(DbBaseController)` + 5 thin routes;
  mutations via `self.transaction.wrap(self.session, ...)`; returns `to_response()`.
- `app/errors/users/{user_not_found_error,user_already_exists_error,forbidden_error}.py`.
- `app/infrastructure/db_session.py` + `app/controllers/db_base_controller.py` — per-request
  `AsyncSession` bound to the IoC for DB-backed routes (Q2). Auth routes keep `get_ioc`.
- `app/services/auth/user_lookup_service.py` — real `UserLookupService` returning an
  `AuthUser` projection (Q1); `app/services/auth/auth_service.py` resolves it; the
  `not_implemented_user_lookup_service.py` stub was removed.
- `app/helpers/security.py` — `require_authentication` route gate (auth-only, Q7).
- `app/mappers/active_user_mapper.py` — `load()` uses integer id; `AuthUser` kept separate.
- `app/main.py` — registers `users_router`.

Verification performed: `import app.main` succeeds with both routers and all 5 user routes
registered; request validators, PATCH `exclude_unset`, and `to_response()` non-leak behavior
checked; all new modules byte-compile. Live DB apply/symmetry and RLS behavior were NOT run
(no `asyncpg`/Docker stack in this environment) — the migration and seed were structurally
reviewed only.

Docs updated: `docs/api/ENDPOINTS.md` (created), `docs/application-stack/auth.md`,
`docs/architecture/IOC.md`, `docs/architecture/CLOUDSALE_PATTERNS.md`,
`docs/plans/2026-05-20-users-layer.md` (superseded).

## Source task

User request (orchestrator-delegated to planner): add a **Users controller** with the
full standard CRUD endpoint set:

- `GET /users` — list all users
- `POST /users` — create a user
- `GET /users/{user_id}` — get a single user
- `PATCH /users/{user_id}` — update a user
- `DELETE /users/{user_id}` — delete a user

Follow the full workflow, starting with the planner; stop after the plan and wait for
user approval before implementing.

> **2026-05-21 scope reconciliation.** This file was first drafted (2026-05-20) for a
> broader "users layer" with a different endpoint set (`GET /users/me`, `GET /users`,
> `POST /users`, `PATCH /users/{user_id}`; **no** single-user GET, **no** DELETE — DELETE
> was explicitly out of scope). The current task **materially changes the endpoint set**:
> it adds `GET /users/{user_id}` and `DELETE /users/{user_id}`. Per the `plan-storage`
> rule "if implementation scope changes materially, update the same plan file and get
> renewed approval," this is an in-place update of the same plan, not a new file. The
> table/Data/Storage/Service/auth-integration/session-binding foundation below is
> unchanged; the **deltas vs the 2026-05-20 draft** are called out in a dedicated section
> ("§0 Endpoint-set deltas"). Renewed user approval is required before any code is written.

This delivers the **Users layer** that the Auth layer deferred: the auth code today wires
`NotImplementedUserLookupService` and `UserStorage` is a 404 stub, because no `users`
table exists yet. This plan implements the real users domain end to end:

- a per-tenant `users` table (Alembic, `client_template` lineage);
- a `User` Data class (`AbstractData`-based) and `UserResponse` shaping that never leaks
  `password_hash`;
- a real `UserStorage` (the only DB-touching layer), every query `tenant_id`-scoped;
- a `UserService` (manager-gated user management business logic, flat-flow errors);
- a real `UserLookupService` backed by `UserStorage`, replacing the
  `NotImplementedUserLookupService` the `AuthService.login` path consumes;
- `/users` endpoints (`GET /users/me`, `GET /users`, `POST /users`,
  `PATCH /users/{user_id}`) on the current IoC + `BaseController` flat-flow pattern;
- domain errors as `ApplicationError` subclasses (the current error pattern);
- docs and seed updates required by RULES.

> **Note on the prior plan.** `docs/plans/2026-05-20-users-layer.md` (`draft`) targets a
> pre-IoC design (`auth/router.py`, `_build_auth_service()`, constructor-injected
> storages, plain-`Exception` errors, `get_db(db_name)` dependency in routes). That design
> no longer matches the codebase: the project now uses the per-request **IoC container**
> (`app/infrastructure/ioc.py`), `BaseController`/`AbstractService`/`AbstractStorage`/
> `AbstractMapper` self-access, the global **`ApplicationError`** handler in `main.py`
> (CloudSale flat-flow, no try/except in controllers), and `AbstractData`/`DataCollection`.
> This plan supersedes it and is written against the **current** architecture. On approval,
> the old plan should be marked superseded by docs-writer.

## Resolved decisions (2026-05-21)

All thirteen open questions were answered by the user. The plan body below still describes
the option space; this section is the authoritative record of what was chosen and is what
all downstream agents must implement.

> **2026-05-21 (final) correction.** An earlier revision of this table recorded Q3 as
> **UUID** and Q7 as a **manager-only gate**. The user's final, authoritative answers
> **override** both: Q3 is an **auto-increment integer PK**, and Q7 (role-based permission
> gates) is **out of scope** — no permission gates on the Users endpoints in this task. The
> table below is the corrected, authoritative record; the older plan body prose that still
> mentions UUID / `require_manager` / manager-only is superseded by this table wherever
> they conflict.

| # | Question | Decision (FINAL, authoritative) |
|---|---|---|
| Q1 | `AuthUser` vs `User` reconciliation | **Keep them separate.** `AuthUser` is the authentication identity and is a distinct concept from the general `User` entity; do **not** conflate or remove `AuthUser`. The real `UserLookupService` returns an `AuthUser` projection built from the `users` row. `UserData` is the management entity. |
| Q2 | IoC session binding (Critical) | **Fix it as part of this task.** Bind a real per-request `AsyncSession` for DB-backed routes so `UserStorage` and `self.transaction.wrap(self.session, ...)` work. Users endpoints are the first DB-backed endpoints, so this infrastructure must be wired. |
| Q3 | UUID vs integer PK | **Auto-increment integer PK** (`BIGINT GENERATED ALWAYS AS IDENTITY`), **not** UUID. DB-generated id assigned back onto the Data object on insert. |
| Q4 | Email type / uniqueness | **`TEXT` + `UNIQUE (tenant_id, email)`** — email is unique **per tenant**, normalized lowercase at the request boundary. |
| Q5 | RLS | **Apply the standard project RLS pattern** — `tenant_id`-based row-level security consistent with the rest of the project. |
| Q6 | `warehouse_full_seed.sql` | **Create/maintain it as the backup/reference PostgreSQL script** per existing convention: add the `users` schema + a clearly-flagged dev-only seed manager per tenant. |
| Q7 | Access control / permissions | **Out of scope.** Do **not** add any role-based permission gates (no `require_manager`, no manager-only service guards) to the Users endpoints in this task. Endpoints require authentication only. |
| Q8 / Q11 | Login tenant routing | **Email is unique per tenant only, never globally; the tenant is always resolved from the credential/token (API key or JWT), never from the email alone.** Full email→tenant registry routing stays out of scope (B1); `UserLookupService` works against the credential-resolved tenant context. |
| Q9 | Password policy | **Numeric PIN: 6–14 digits, integers only.** Validate at the request boundary (digits-only, length 6–14). Still bcrypt-hashed before storage. |
| Q10 | Response shape | **Return `UserData` directly as the response, with the password/`password_hash` field excluded.** Serialize via `UserData` (a `to_response()`/safe-dict that omits `password_hash`). The serialized response must never include `password_hash`. |
| Q12 | Delete semantics | **Hard delete.** Plus a **self-delete guard**: a user cannot delete their own account (403). |
| Q13 | `GET /users/me` | **Out of scope for this task** — it gets its own separate `/me` controller later. Do **not** add `/users/me` here. The endpoint set is exactly the 5 CRUD routes. |

### Consequences for the build

- **Endpoint set is exactly 5 routes** (no `/users/me`): `GET /users`, `POST /users`,
  `GET /users/{user_id}`, `PATCH /users/{user_id}`, `DELETE /users/{user_id}` —
  authentication-required only (no role gate, Q7).
- **No permission gates** (Q7): no `require_manager` dependency, no manager-only service
  guard. Routes require a valid credential (`ActiveUserMapper.is_initialized()`); any
  authenticated user may call any Users endpoint. Role-based authorization is a later task.
- **Integer PK** (Q3): `users.id` is an auto-increment `BIGINT IDENTITY`. `UserData.id`
  is `int`; storage assigns the DB-generated id back onto the Data object on insert.
- **`AuthUser` stays** (Q1): `app/data/auth_user.py` is **not** removed;
  `ActiveUserMapper` and `ApiKeyStorage` keep their `AuthUser` type refs. The real
  `UserLookupService.get_by_email` returns `AuthUser | None` (projection from the row).
- **Password is a numeric PIN** (Q9): the request layer validates digits-only, length
  6–14. Still bcrypt-hashed via `hash_password` before storage (never stored in clear).
- **Response is `UserData` minus `password_hash`** (Q10): no separate Pydantic
  `UserResponse` model — `UserData` exposes a response-shaping method that omits
  `password_hash`. `UserData.to_dict()` (which includes `password_hash`) must never be
  returned raw.
- **Hard delete + self-delete guard** (Q12): `DELETE FROM users WHERE tenant_id AND id`;
  no `deleted_at` column. Service raises 403 if `user_id == ActiveUserMapper.user_id`.
- **Session binding is in scope** (Q2): implementer wires a per-request `AsyncSession`
  bound to the IoC for DB-backed routes (Users are the first such endpoints).

## Existing code this builds on (verified against current source)

| File | Relevance |
|---|---|
| `app/infrastructure/ioc.py` | per-request `Ioc`; resolves `*Service`/`*Storage`/`*Mapper` by class name → snake_case module; `*Error` via `ErrorFactory.get(...)`; carries `session`, `claims`, `tenant_id`, `redis`, `settings`, `transaction`. |
| `app/controllers/base_controller.py` | `BaseController.__init__(ioc = Depends(get_ioc))`; `self.<ClassName>` proxies to the IoC. New controller extends this. |
| `app/controllers/auth/auth.py` | flat-flow controller + thin-route precedent (`ctrl: AuthController = Depends(AuthController)`); pattern to mirror for `/users`. |
| `app/services/abstract_service.py` | `AbstractService(ioc)` base; `self.UserStorage`, `self.settings`, `self.ActiveUserMapper`, `self.<Error>` access. |
| `app/services/auth/auth_service.py` | flat-flow service precedent; `self.NotImplementedUserLookupService.get_by_email(email, db_name)`; raises `self.InvalidCredentialsError.get(...)`. The `user_lookup`/`db_name` lines change here. |
| `app/services/auth/not_implemented_user_lookup_service.py` | `UserLookup` Protocol (`get_by_email(email, db_name) -> AuthUser \| None`) + the `NotImplementedUserLookupService` stub to replace with a real `UserLookupService`. |
| `app/storages/abstract_storage.py` | `AbstractStorage(ioc)`; read `self.session`, `self.tenant_id`, `self.redis`; never take them as params. |
| `app/storages/user_storage.py` | current **404 stub** (`get_by_id` raises). Replaced by the real `UserStorage`. |
| `app/storages/refresh_token_storage.py` | reference storage style on the IoC base (methods take only domain args, pull resources from `self`). |
| `app/mappers/active_user_mapper.py` | identity read surface: `is_initialized()`, `user_id`, `tenant_id`, `role`, `is_admin()`, `is_manager()`; `load()` calls `self._ioc.UserStorage.get_by_id(self.user_id)` and returns `AuthUser`. Affected by the `UserStorage`/`AuthUser` reconciliation (Q1, Q7). |
| `app/data/auth_user.py` | `AuthUser(id, tenant_id, email, role, password_hash)` plain dataclass; same entity as `User`. Reconciliation decision Q1. |
| `app/data/abstract_data.py` | `AbstractData` base (`FIELDS`, `from_row`, `fix_type`, `to_dict`, field guard). `User` extends this. |
| `app/data/data_collection.py` | `DataCollection[T]` for `list_users` shaping (`to_dicts()`). |
| `app/data/token.py` | `TokenData(sub, tenant_id, role)` — claims source; identity for endpoints (via `ActiveUserMapper`). |
| `app/errors/application_error.py` | `ApplicationError` base (`http_status`, `detail`, `headers`, `export()`); global handler in `main.py`. New user errors subclass this. |
| `app/errors/auth/invalid_credentials_error.py` | error-subclass precedent (class attrs only). |
| `app/requests/auth/login_request.py` | Pydantic `BaseModel` request precedent (`EmailStr`). |
| `app/helpers/password.py` | `hash_password` / `verify_password` (passlib bcrypt) — used by `UserService`. |
| `app/infrastructure/transaction.py` | `TransactionHelper.wrap(session, func, ...)`; controller wraps mutations via `self.transaction.wrap(self.session, ...)`. |
| `app/infrastructure/database.py` | `get_db(db_name)`, `get_session(db_name)`, `get_engine` (NullPool, prepared-stmt cache off for PgBouncer). Relevant to whether `/users` requests get a bound session (see Q2/Q6). |
| `app/infrastructure/ioc.py::get_ioc` | binds `session=None` today. **Gap:** mutations on `/users` need a real session bound to the IoC — see Q2 (Critical). |
| `alembic/env.py`, `alembic.ini` | multi-DB Alembic; `client_template` section → `alembic/versions/client_template/` (currently only `.keep`; this is the first revision, `down_revision = None`). |
| `docker/init-db.sql` | bootstraps `aton_clients` + `client_template`; extension bootstrap (pgcrypto/citext) would go here or in the migration. |
| `app/main.py` | registers `auth_router`; must register `users_router`; already has the `ApplicationError` + validation handlers. |

## Plan contract fields

- **Implementation owner:** `implementer` (all `app/` files), `database` (migration + seed +
  extensions), `docs-writer` (docs + plan status), `spec-writer` (plain-language feature),
  `security` (post-review), `version-control` (final commit).
- **UI scope:** none.
- **Database scope:** required (new table, enum, constraint, RLS, first `client_template`
  revision, seed).
- **Security scope:** required (auth-path change, multi-tenant isolation, password
  handling, manager authorization, credential non-leakage, seed credentials).
- **Docs scope:** required (`docs/api/ENDPOINTS.md`, `docs/application-stack/auth.md`,
  plan status; supersede old plan).

## Scope

### 0. Endpoint-set deltas vs the 2026-05-20 draft (read this first)

The current task's endpoint list is the standard 5-route CRUD set. Mapped against the
older draft:

| Endpoint (current task) | In old draft? | Delta |
|---|---|---|
| `GET /users` (list) | yes (manager-only) | unchanged |
| `POST /users` (create) | yes (manager-only) | unchanged |
| `GET /users/{user_id}` (single) | **no** | **NEW** — add `UserStorage.get_by_id` is already planned; add a `get_user(user_id)` service method + route. |
| `PATCH /users/{user_id}` (update) | yes | unchanged |
| `DELETE /users/{user_id}` (delete) | **no — explicitly out of scope** | **NEW** — adds a `delete` storage method, `delete_user` service method, a route, and a `users.deleted_at`/hard-delete decision (Q12). |
| `GET /users/me` | yes | **Not in the current task list.** Recommend **keeping** it (cheap, already designed, the natural "read own profile" route and the one any-authenticated-role read). Confirm at approval (Q13). |

Two genuinely new design questions this raises — see Q12 (delete semantics: hard vs soft)
and Q13 (`/users/me` keep vs drop) in "Open questions for approval". Everything else in
this plan (table, Data, Storage foundation, Service gating, auth integration, session
binding, errors, requests) stands as previously drafted.

### 1. Database — `users` table (per-tenant, `client_template` lineage)

First revision under `alembic/versions/client_template/` (`down_revision = None`),
generated via `alembic -n client_template revision -m "create users table"`.

Columns:

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | app-side `uuid4` (Q3) → no extension dependency, matches `str(id)` in `from_row` |
| `tenant_id` | `UUID NOT NULL` | tenant scope (defense in depth even in a tenant-private DB) |
| `email` | `TEXT NOT NULL` | normalized lowercase at the request boundary (Q4) |
| `password_hash` | `TEXT NOT NULL` | bcrypt; never logged, never serialized |
| `role` | `user_role` enum (`manager`, `staff`) `NOT NULL` | Postgres `ENUM` |
| `created_at` | `TIMESTAMPTZ NOT NULL` | server default `now()` |
| `updated_at` | `TIMESTAMPTZ NOT NULL` | server default `now()`; bumped on update |

Constraints / indexes (documented access patterns only):

- PK on `id` (serves `get_by_id`, which still adds `AND tenant_id = :tenant_id`).
- `UNIQUE (tenant_id, email)` — enforces per-tenant email uniqueness **and** backs the
  hot `get_by_email` lookup (no separate index).

RLS (Q5): `ALTER TABLE users ENABLE ROW LEVEL SECURITY;` plus a tenant-isolation policy
keyed off a session GUC (`current_setting('app.tenant_id', true)`). Because nothing sets
that GUC today, a strict policy would silently return 0 rows. **Recommended:** enable RLS
now with a policy written correctly for the GUC, but ship it **permissive-until-GUC-wired**
(or `USING (true)` with a TODO) so reads do not break, and wire the GUC + strict policy in
the tenant-routing task. The database/security agents own the exact policy text and
PgBouncer-`SET LOCAL` interaction.

`upgrade()`: create `user_role` enum → create `users` → add `UNIQUE (tenant_id, email)` →
enable RLS + policy. `downgrade()`: drop policy → drop `users` → drop `user_role`.

### 2. Seed / schema SQL (RULES requirement)

RULES: "New tables require `warehouse_full_seed.sql` updates with schema and seed data."
This file does not exist (Q6). **Recommended:** create `warehouse_full_seed.sql` (repo
root) with the `users` schema + at least one **dev-only** seed manager per tenant
(bcrypt-hashed placeholder password, clearly flagged dev-only, never a real secret). The
database agent owns location + seed content; security reviews the seed credential. Do not
silently skip this RULES requirement.

### 3. Data layer

`app/data/user.py` — `User(AbstractData)`:

- `FIELDS = {id: STRING, tenant_id: STRING, email: STRING, password_hash: STRING,
  role: STRING, created_at: DATETIME, updated_at: DATETIME}`.
- `@dataclass` with fields matching `FIELDS`; rely on `AbstractData.from_row`/`fix_type`
  (datetimes → tz-aware UTC). No business logic.
- `to_dict()` includes `password_hash` — so `User.to_dict()` must **never** be returned
  directly from a controller (Q10 covers the safe response shape).

`UserResponse` (Q10) — recommended a Pydantic `BaseModel` in
`app/requests/users/user_response.py` (or `app/controllers/users/responses.py`) with
`id, tenant_id, email, role, created_at, updated_at` (NO `password_hash`); built from a
`User` via an explicit mapper/classmethod. This is the only shape returned to clients.
`created_at`/`updated_at` serialized ISO 8601 UTC (`...Z`).

**`AuthUser` reconciliation (Q1).** `AuthUser` and `User` are the same entity. `AuthService`
and `ActiveUserMapper.load()` read only `id, tenant_id, email, role, password_hash` (the
shared subset). Options:

- **(A, recommended)** Make `User` canonical and remove `AuthUser`; update
  `UserLookupService`/`AuthService`/`ActiveUserMapper`/`ApiKeyStorage` type refs to `User`.
  `User` is a superset, so reads stay source-compatible. One entity for one thing
  (avoids the RULES "two entities for one thing" anti-pattern). `AuthUser`'s "no
  `to_dict()` leak" guarantee is preserved by **never** serializing `User` directly
  (UserResponse is mandatory) + reviewer/security check.
- **(B)** Keep `AuthUser` as a narrow auth projection; the real `UserLookupService` builds
  an `AuthUser` from a `User` row. More indirection, two classes.

Recommend **A**, but flag that it touches `ApiKeyStorage` and `ActiveUserMapper` type
hints (still stubs, low risk). If the user prefers minimal blast radius, **B** keeps
`AuthUser` untouched.

### 4. Storage layer

`app/storages/user_storage.py` — replace the 404 stub with the real `UserStorage`
(`AbstractStorage`). All methods `async`; read `self.session` and `self.tenant_id` from
the IoC (never as params); **every query filters by `tenant_id`**; never start a
transaction; return `User` / `DataCollection[User]` / `None` only; assign generated
`id`/timestamps back onto the passed `User` on insert. SQLAlchemy Core (`text()`), since
no ORM models exist.

| Method | Signature | Behavior |
|---|---|---|
| `get_by_email` | `(email: str) -> User \| None` | `WHERE tenant_id = :tid AND email = :email`. |
| `get_by_id` | `(user_id: str) -> User \| None` | `WHERE tenant_id = :tid AND id = :id`. (Replaces the stub signature used by `ActiveUserMapper.load()`.) |
| `create` | `(user: User) -> User` | `INSERT ... RETURNING`; assign generated `id`/`created_at`/`updated_at` back onto `user`. |
| `update` | `(user: User) -> User` | `UPDATE ... WHERE tenant_id = :tid AND id = :id`; bump `updated_at`; `RETURNING`. |
| `list` | `() -> DataCollection[User]` | `WHERE tenant_id = :tid ORDER BY created_at` (stable order). |
| `delete` | `(user_id: str) -> bool` (NEW) | hard delete `DELETE ... WHERE tenant_id = :tid AND id = :id` (Q12 default), or soft delete (`UPDATE ... SET deleted_at = now()`) if Q12 picks soft. Returns whether a row was affected so the service can raise `UserNotFoundError` on a miss. `tenant_id`-scoped. |

> **Login-path tenant_id (Q2 + Q8).** `get_by_email` uses `self.tenant_id`, which comes
> from JWT claims — but **at login there is no JWT**, so `tenant_id` is `None`. The real
> login lookup needs a tenant-scoped query without claims. Resolution options under Q8.
> The current `AuthService.login` also passes `db_name=settings.alembic_shared_db`
> (the registry), not a tenant DB — a pre-existing routing gap. See §6 + Q8.

### 5. Service layer

`app/services/users/user_service.py` — `UserService(AbstractService)`. Flat-flow (no
try/except); business logic only; never starts a transaction; never touches the DB
directly; resolves collaborators via `self.UserStorage`, `self.ActiveUserMapper`,
`self.<Error>`. **Identity (`user_id`, `tenant_id`, `role`) is read only via
`self.ActiveUserMapper`** — never from request input. Authorization is manager-only for
create/update/list (Q7).

| Method | Signature (proposed) | Logic |
|---|---|---|
| `get_me` | `() -> User` | (kept pending Q13) `user_id = self.ActiveUserMapper.user_id`; `UserStorage.get_by_id(user_id)`; `UserNotFoundError` if `None`. Any authenticated role. |
| `get_user` | `(user_id: str) -> User` (NEW) | manager gate; `UserStorage.get_by_id(user_id)`; `UserNotFoundError` if `None`. Backs `GET /users/{user_id}`. `user_id` is a path arg, but the lookup is still `tenant_id`-scoped via storage, so a manager cannot read another tenant's user. |
| `create_user` | `(email, password, role) -> User` | manager gate (Q7); `get_by_email` → `UserAlreadyExistsError` if taken; `hash_password(password)`; build `User` with `tenant_id = self.ActiveUserMapper.tenant_id`; `UserStorage.create`. |
| `update_user` | `(user_id, fields: dict) -> User` | manager gate; `get_by_id` → `UserNotFoundError` if missing; apply only submitted fields (`email`, `password`→hash, `role`); re-check uniqueness on email change; `UserStorage.update`. |
| `delete_user` | `(user_id: str) -> None` (NEW) | manager gate; **self-delete guard**: if `user_id == self.ActiveUserMapper.user_id` raise `ForbiddenError` (a manager must not delete their own account out from under the live session — Q12 sub-decision, recommended); `UserStorage.delete(user_id)` → `UserNotFoundError` if no row affected. Hard vs soft per Q12. |
| `list_users` | `() -> DataCollection[User]` | manager gate; `UserStorage.list()`. |

Manager gate (Q7): a `require_manager` FastAPI dependency at the route boundary (clean
403) **and** a defensive `self.ActiveUserMapper.is_manager()` check in the service raising
`ForbiddenError` (defense in depth). Recommended: both. The gate must use the new role
vocabulary (`manager`/`staff`) — note `ActiveUserMapper` currently knows `admin`/`manager`
(`_ROLE_ADMIN`/`_ROLE_MANAGER`); `staff` is a non-manager. Reviewer to confirm role
literals align with the `user_role` enum.

### 6. Auth integration — real `UserLookupService`

Replace `NotImplementedUserLookupService` with a real `app/services/auth/user_lookup_service.py`
(`UserLookupService(AbstractService)`) backed by `UserStorage`, implementing
`get_by_email(email, db_name) -> User | None` (return type `User` under Q1-A, else
`AuthUser`). Update `AuthService.login` to resolve `self.UserLookupService` instead of
`self.NotImplementedUserLookupService`.

**Login tenant scoping (Q8 — Critical).** Two coupled gaps:

1. `UserStorage.get_by_email` filters by `self.tenant_id`, but at login `claims is None`
   so `tenant_id` is `None`. 2. `login` passes the registry DB (`aton_clients`), not a
   tenant DB; users live in `client_{slug}` DBs.

Options:

- **(B1, recommended for this task's scope)** Keep full email→tenant routing **out of
  scope**. Implement `UserLookupService` to query a **given tenant DB** by email (the DB
  is tenant-private, so email is unambiguous). For the `tenant_id` filter, either (a) the
  lookup uses a session bound to a single configured tenant DB and selects by email,
  reading `tenant_id` off the returned row, or (b) add a narrow storage path for the
  no-claims login case. Document the interim `db_name` `login` uses. Full
  registry-driven routing (`email → aton_clients → client_{slug} + tenant_id`) is the
  named follow-up task.
- **(B2)** Pull minimal registry routing into this task (larger; the auth plan deferred
  it). Not recommended here.

This is the highest-uncertainty area — the security + database agents must review the
interim trust boundary at approval. The login path may remain not-fully-wired end to end
(documented) until routing lands; users CRUD on authenticated `/users` routes is fully
functional regardless.

### 7. Request / session binding for `/users` (Q2 — Critical, cross-cutting)

`get_ioc` currently binds `session=None`, and `self.session` raises `IocResolutionError`.
The auth controller works only because it is Redis-only. **`/users` mutations need a real
`AsyncSession` bound to the IoC** so `UserStorage` can query and `self.transaction.wrap(
self.session, ...)` can commit. This is a genuine infrastructure gap, not just a feature.

Options (database/implementer + user decide):

- **(2a, recommended)** Add session binding to the IoC bootstrap: a dependency that opens
  a tenant session (`get_db`/`get_session`) and a way for `get_ioc` (or a sibling
  dependency the `/users` controller uses) to bind it onto the `Ioc`. Smallest correct
  change that respects "storage reads `self.session`". Requires deciding which tenant DB
  the request targets — for now the configured tenant/template DB until routing lands
  (ties to Q8).
- **(2b)** A `/users`-specific controller dependency that constructs the `Ioc` with a
  session. More local but duplicates `get_ioc`.

This MUST be resolved before storage/controller code is written; it gates all DB-backed
endpoints (not only users). Flagged for the database agent.

### 8. Requests

`app/requests/users/create_user_request.py` — `CreateUserRequest(BaseModel)`:
`email: EmailStr` (trim + lowercase normalized, matching the storage email semantics from
Q4), `password: str` (min length, Q9 → recommend ≥ 8), `role: Literal["manager", "staff"]`.

`app/requests/users/update_user_request.py` — `UpdateUserRequest(BaseModel)`, PATCH
semantics: all of `email`/`password`/`role` optional; validate **only** submitted fields
via `model_fields_set`; service applies only `model_dump(exclude_unset=True)`. All
validation at the boundary; downstream trusts it.

### 9. Controllers / Endpoints

`app/controllers/users/users.py` — `UsersController(BaseController)` + thin routes,
mirroring `auth.py`. `APIRouter(prefix="/users", tags=["users"])`, registered in
`main.py`. No business logic, no DB access; identity via `self.ActiveUserMapper`;
mutations via `self.transaction.wrap(self.session, ...)`; returns `UserResponse`.

| Method | Path | Auth | Body | Returns |
|---|---|---|---|---|
| `GET` | `/users/me` | any authenticated | — | `UserResponse` (kept pending Q13) |
| `GET` | `/users` | manager only | — | `list[UserResponse]` |
| `POST` | `/users` | manager only | `CreateUserRequest` | `UserResponse`, 201 |
| `GET` | `/users/{user_id}` | manager only | — | `UserResponse` (NEW) |
| `PATCH` | `/users/{user_id}` | manager only | `UpdateUserRequest` | `UserResponse` |
| `DELETE` | `/users/{user_id}` | manager only | — | `204 No Content` (NEW) |

> **Route ordering:** declare the literal `GET /users/me` route **before** the
> `GET /users/{user_id}` parameterized route so `me` is not captured as a `user_id`
> path value (only relevant if Q13 keeps `/users/me`).

- Auth enforcement: routes require auth (the IoC `claims` must be present;
  `ActiveUserMapper.is_initialized()` / a `get_current_user`-equivalent gate). Manager
  routes additionally use the `require_manager` dependency (Q7). 401 when unauthenticated,
  403 when authenticated non-manager.
- `DELETE` returns `204 No Content` (mirrors `auth.logout`'s `Response(status_code=204)`),
  via `self.transaction.wrap(self.session, ...)` like the other mutations.
- `password_hash` never returned (UserResponse strips it) and never logged.

### 10. Errors

`app/errors/users/` — `ApplicationError` subclasses (current pattern; class attrs only),
resolved via `self.<Name>Error.get(...)`:

| File / class | http_status | When |
|---|---|---|
| `user_not_found_error.py` / `UserNotFoundError` | 404 | `get_me`/`get_user`/`update_user`/`delete_user` target missing |
| `user_already_exists_error.py` / `UserAlreadyExistsError` | 409 | create/update with a taken email (also catch the unique-constraint race) |
| `forbidden_error.py` / `ForbiddenError` | 403 | non-manager calling a manager-only method, or a manager attempting self-delete (service defense in depth) |

The new `GET /users/{user_id}` and `DELETE /users/{user_id}` routes reuse the same three
error classes — no new error classes are introduced by the endpoint-set delta.

Unique error codes; mapped to HTTP automatically by the global handler (no controller
try/except). Each `*Error` lives in its own snake_case module (IoC `*Error` resolution).

### 11. main.py

Register `users_router` alongside `auth_router`.

## Out of scope

- Email→tenant routing / registry-driven login resolution (the named follow-up; Q8-B1).
- Self-service signup/registration (managers create users).
- Password reset / email verification / change-own-password.
- ~~User deletion~~ — **now in scope** (`DELETE /users/{user_id}`, manager-only). Account
  *deactivation* (`is_active` toggle) and bulk delete remain out of scope.
- Pagination / filtering / search on `GET /users`.
- Rate limiting on `/users`.
- Fanning the migration out to live `client_{slug}` DBs (provisioning task).
- Frontend / UI.
- Implementing the `api_keys` table / real `ApiKeyStorage` (only its `AuthUser`→`User`
  type ref changes if Q1-A is chosen).

## Acceptance criteria

- `client_template` revision creates `users` with all required columns, the `user_role`
  enum (`manager`/`staff`), `UNIQUE (tenant_id, email)`, and RLS enabled; `upgrade`/
  `downgrade` symmetric; `alembic -n client_template upgrade head` applies cleanly.
- `User(AbstractData)` field names match DB columns; `from_row` builds a `User`; timestamps
  tz-aware UTC; no business logic. `User`/`password_hash` is never returned by any endpoint
  (UserResponse only) and never logged.
- `AuthUser` reconciled per the approved option; `AuthService` and `ActiveUserMapper`
  behave identically; no dangling `AuthUser` imports if removed (A).
- `UserStorage` exposes `get_by_email`, `get_by_id`, `create`, `update`, `list`, `delete`;
  **every** query filters by `tenant_id`; `create` assigns generated `id`/timestamps back;
  reads/lists return only `User`/`DataCollection[User]`/`None`, `delete` returns a bool;
  starts no transaction; reads `self.session`/`self.tenant_id` from the IoC.
- `GET /users/{user_id}` returns the requested user as `UserResponse` (manager-only;
  cross-tenant id → 404 via `tenant_id`-scoped lookup, never another tenant's record).
- `DELETE /users/{user_id}` removes the user (hard or soft per Q12), returns `204`;
  unknown/cross-tenant id → 404; a manager deleting their own account → 403 (self-delete
  guard); manager-only (403 for staff, 401 unauthenticated).
- A real `UserLookupService` backed by `UserStorage` replaces
  `NotImplementedUserLookupService` in `AuthService.login`; the wired login path no longer
  raises `NotImplementedError` (interim tenant scoping per Q8 documented).
- `/users` requests get a real `AsyncSession` bound to the IoC (Q2); mutations commit via
  `self.transaction.wrap(self.session, ...)`.
- `UserService`: manager-only on create/update/list; `get_me` for any authenticated role;
  duplicate-email rejected; PATCH applies only submitted fields and re-checks uniqueness on
  email change; bcrypt hashing via `hash_password`; no transactions; no direct DB; identity
  only via `ActiveUserMapper`.
- `CreateUserRequest` validates `email`/`password`/`role`; `UpdateUserRequest` validates
  only submitted fields (`model_fields_set`/`exclude_unset`).
- Endpoints behave per the table; manager routes 403 for `staff`, 401 unauthenticated;
  `POST` returns 201; timestamps ISO 8601 UTC.
- `tenant_id`/`role` read only from verified claims (via `ActiveUserMapper`) — never from
  body/query/path.
- New user errors are `ApplicationError` subclasses with unique codes, resolved via
  `self.<Name>Error.get(...)`, mapped by the global handler (no controller try/except).
- `warehouse_full_seed.sql` created with `users` schema + dev-only seed (per RULES) unless
  deferred at approval.
- `python -c "import app.main"` imports cleanly with both routers registered.
- All new code: full type hints, `logging` not `print`, no mutable default args, layer
  boundaries respected.

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `alembic/versions/client_template/<rev>_create_users_table.py` | created (first `client_template` revision) | database |
| `warehouse_full_seed.sql` | created (schema + dev-only seed) | database |
| `docker/init-db.sql` | updated only if an extension bootstrap is needed (Q3/Q4 → likely not, app-side uuid + TEXT) | database |
| `app/infrastructure/ioc.py` (+ `get_ioc` / a session dependency) | updated to bind an `AsyncSession` for DB-backed routes (Q2) | implementer (database to confirm session/PgBouncer interaction) |
| `app/data/user.py` | created (`User(AbstractData)`) | implementer |
| `app/data/auth_user.py` | removed (A) or kept (B) | implementer |
| `app/requests/users/__init__.py` | created | implementer |
| `app/requests/users/create_user_request.py` | created | implementer |
| `app/requests/users/update_user_request.py` | created | implementer |
| `app/requests/users/user_response.py` (or `controllers/users/responses.py`) | created (`UserResponse`, no `password_hash`) | implementer |
| `app/storages/user_storage.py` | replaced (real `UserStorage`, incl. `get_by_id`, `list`, `delete`) | implementer |
| `app/services/users/__init__.py` | created | implementer |
| `app/services/users/user_service.py` | created (`UserService`) | implementer |
| `app/services/auth/user_lookup_service.py` | created (real `UserLookupService`) | implementer |
| `app/services/auth/not_implemented_user_lookup_service.py` | removed or kept as fallback (confirm) | implementer |
| `app/services/auth/auth_service.py` | updated (resolve `UserLookupService`; revisit `db_name`, Q8) | implementer |
| `app/mappers/active_user_mapper.py` | updated only for `AuthUser`→`User` type ref (A) | implementer |
| `app/storages/api_key_storage.py` | updated only for `AuthUser`→`User` type ref (A) | implementer |
| `app/controllers/users/__init__.py` | created | implementer |
| `app/controllers/users/users.py` | created (`UsersController` + 5–6 routes incl. single-GET + DELETE) | implementer |
| `app/helpers/security.py` (or a mappers/deps location) | updated/added (`require_manager` dependency) | implementer |
| `app/errors/users/__init__.py` | created | implementer |
| `app/errors/users/user_not_found_error.py` | created | implementer |
| `app/errors/users/user_already_exists_error.py` | created | implementer |
| `app/errors/users/forbidden_error.py` | created | implementer |
| `app/main.py` | updated (register `users_router`) | implementer |
| `docs/api/ENDPOINTS.md` | created with `/users` contracts (file does not exist) | docs-writer |
| `docs/application-stack/auth.md` | updated (users table / endpoints now implemented) | docs-writer |
| `docs/plans/2026-05-20-users-layer.md` | marked superseded by this plan | docs-writer |
| `docs/plans/2026-05-20-users-endpoint.md` | status → `implemented` + "What was built" after build | docs-writer |

## Risks

- **Session-binding gap (Q2) is infrastructure, not just a feature.** `get_ioc` binds
  `session=None`; `/users` is the first DB-backed endpoint. Getting the per-request
  session + PgBouncer (`SET LOCAL` for any RLS GUC) right is the biggest risk.
  Mitigation: resolve Q2 with the database agent before writing storage/controller code.
- **Login tenant scoping (Q8).** `get_by_email` needs a `tenant_id` that does not exist
  pre-JWT, and `login` targets the registry DB. End-to-end login may stay partly wired
  until routing lands. Mitigation: scope routing out (B1), document interim `db_name`,
  security-review the interim boundary.
- **`AuthUser` reconciliation (Q1-A).** Removing `AuthUser` touches `AuthService`,
  `ActiveUserMapper`, `ApiKeyStorage` type refs. Mitigation: `User` is a superset; reviewer
  greps for residual `AuthUser` imports. B avoids this entirely.
- **RLS vs missing GUC (Q5).** A strict policy with no GUC set → silent empty reads.
  Mitigation: ship permissive-until-wired, enforce in the routing task; `SET LOCAL` under
  PgBouncer transaction pooling.
- **`password_hash` leakage.** `User.to_dict()` includes it. Mitigation: mandatory
  `UserResponse`; reviewer/security confirm no endpoint serializes raw `User` and it is
  never logged.
- **Email case semantics (Q4).** Request normalization must match the DB unique key and
  the login lookup, or duplicates/failed logins result. Decide once; apply in request +
  storage + migration.
- **Role vocabulary drift.** `ActiveUserMapper` knows `admin`/`manager`; the user enum is
  `manager`/`staff`. The manager gate and seeded roles must use enum literals. Reviewer
  confirms alignment (and whether `admin` remains a valid superset).
- **`warehouse_full_seed.sql` seed credentials.** Dev-only, clearly flagged; security
  reviews. Never a real secret.
- **No live DB/Redis in CI.** Verification limited to imports + unit-level behavior unless
  the Docker stack is started for integration.

## Plan (execution order)

1. **planner** — this plan (no code). Stop for user approval (Decision Order step 2).
2. **database** — resolve Q3/Q4/Q5/Q6 + Q2 session/PgBouncer interaction; write & run the
   `client_template` migration; create `warehouse_full_seed.sql`; confirm migration symmetry
   and that RLS does not silently break reads.
3. **implementer** — IoC session binding (Q2); `User` Data + `UserResponse`; `UserStorage`;
   `UserService`; requests; errors; `require_manager`; `UsersController` + routes; real
   `UserLookupService` + `AuthService` wiring; `AuthUser` reconciliation; `main.py`.
4. **reviewer** — layer boundaries (controller no logic/DB; service no txn/DB; storage only
   DB + always `tenant_id`-filtered; Data only `from_row`); PATCH only submitted fields;
   `password_hash` never returned/logged; manager gate enforced; identity only via
   `ActiveUserMapper`; type hints; no `print`; `AuthUser` swap leaves no dangling imports.
5. **security** — real `UserLookupService` tenant scoping + login routing gap (Q8); RLS
   correctness + GUC/`SET LOCAL`; per-tenant email uniqueness vs enumeration;
   `password_hash` non-leakage; manager-only authorization (no escalation via
   request-supplied `role`/`tenant_id`); seed credential exposure.
6. **docs-writer** — create `docs/api/ENDPOINTS.md` (`/users` contracts); update
   `docs/application-stack/auth.md`; supersede the old plan; set this plan `implemented`
   with "What was built".
7. **spec-writer** — plain-language description (a manager creates/lists/updates users;
   roles manager/staff; everyone views their own profile).
8. **version-control** — commit plan + migration + seed + code + docs together at the end.

## Validation notes

- `python -c "import app.main"` after implementation (both routers registered, no import
  errors from the `AuthUser` swap).
- `alembic -n client_template upgrade head` then `downgrade base` against the Docker stack
  (symmetry); structural review regardless of live DB.
- Manual/integration: `POST /users` as manager → 201; as staff → 403; unauthenticated →
  401; `GET /users/me` returns the caller without `password_hash`; `GET /users/{id}` as
  manager → 200, cross-tenant id → 404; PATCH updates only submitted fields; duplicate
  email → 409; `DELETE /users/{id}` → 204, unknown id → 404, self-delete → 403, gone after
  delete (`GET` → 404).

## Open questions for approval

> **All resolved 2026-05-21.** See "Resolved decisions (2026-05-21)" for the authoritative
> table. Each question's outcome is recorded inline below.

1. **`AuthUser` reconciliation** — **RESOLVED: Option B.** Keep `AuthUser` and `User`
   **separate**; authentication identity is a distinct concept from the general user
   entity. Do not remove `AuthUser`. `UserLookupService` returns an `AuthUser` projection.
2. **(Critical) IoC session binding** — **RESOLVED: 2a, fix as part of this task.** Bind a
   real per-request `AsyncSession` for DB-backed routes. Database agent validates the
   PgBouncer/session interaction; implementer wires it.
3. **PK type** — **RESOLVED: auto-increment integer** (`BIGINT IDENTITY`), **not** UUID.
   DB-generated id assigned back onto the Data object on insert.
4. **Email type/case** — **RESOLVED: `TEXT` + `UNIQUE (tenant_id, email)`**, lowercase on
   input. Email is unique per tenant only.
5. **RLS** — **RESOLVED: apply the standard project RLS pattern** (tenant_id-based,
   consistent with other tables). Database agent owns the exact policy text.
6. **`warehouse_full_seed.sql`** — **RESOLVED: create/maintain it** as the backup/reference
   PostgreSQL script per existing convention, with the `users` schema + a dev-only seed
   manager.
7. **Access control / permissions** — **RESOLVED: out of scope.** Do **not** add any
   role-based permission gates (no `require_manager` dependency, no manager-only service
   guard) to the Users endpoints in this task. Endpoints require authentication only;
   role-based authorization is a separate later task.
8. **(Critical) Login tenant routing** — **RESOLVED: B1.** Email is unique per tenant only,
   never globally; tenant is always resolved from the credential/token, never from the
   email. Full email→tenant registry routing stays out of scope.
9. **Password policy** — **RESOLVED: numeric PIN, 6–14 digits, integers only.** Validated
   at the request boundary; still bcrypt-hashed before storage.
10. **Response shape** — **RESOLVED: return `UserData` directly with `password_hash`
    excluded.** No separate Pydantic response model required; strip `password_hash` from
    the serialization. `User.to_dict()` (includes `password_hash`) is never returned raw.
11. **`NotImplementedUserLookupService`** — **RESOLVED (folds into Q8).** Replaced by the
    real `UserLookupService`; remove the stub (or keep documented) per implementer's
    minimal-blast-radius judgement — the real service is what `AuthService.login` resolves.
12. **(NEW) Delete semantics** — **RESOLVED: hard delete + self-delete guard.**
    `DELETE FROM users ...`; no `deleted_at` column. A manager cannot delete their own
    account (403).
13. **(NEW) `GET /users/me`** — **RESOLVED: out of scope.** `/users/me` gets its own
    separate `/me` controller in a later task. The endpoint set here is exactly the 5 CRUD
    routes — do **not** add `/users/me`.

## Approval log

- 2026-05-20: plan drafted, status `draft`. Supersedes `2026-05-20-users-layer.md` (stale,
  pre-IoC design). Eleven open questions; Q2 and Q8 blocking/critical. No approval recorded.
- 2026-05-21: plan updated in place for a **material endpoint-set change** (orchestrator-
  delegated). Added `GET /users/{user_id}` and `DELETE /users/{user_id}` (see §0 deltas);
  added `UserStorage.delete`, service `get_user`/`delete_user`, the two routes, and two new
  open questions (Q12 delete semantics, Q13 `/users/me` keep/drop). No new error classes.
- 2026-05-21: **user answered all thirteen open questions** (orchestrator-delegated).
  Decisions recorded in "Resolved decisions (2026-05-21)"; each open question marked
  RESOLVED. Status → `approved`.
- 2026-05-21 (final correction): the user's authoritative final answers **override** two
  earlier entries — **Q3 is an auto-increment integer PK** (not UUID) and **Q7 access
  control is out of scope** (no permission gates of any kind on Users endpoints). The
  Resolved-decisions table, "Consequences for the build", and the inline RESOLVED list were
  corrected to match. Net authoritative scope: **keep `AuthUser` separate** (Q1);
  **session binding fixed in-task** (Q2); **integer PK / TEXT email / per-tenant unique**
  (Q3/Q4); **standard project RLS** (Q5); **seed file maintained** (Q6); **no permission
  gates** (Q7); **tenant from credential, email unique per tenant** (Q8/Q11); **numeric PIN
  6–14 digits** (Q9); **return `UserData` minus `password_hash`, no separate response
  model** (Q10); **hard delete + self-delete guard** (Q12); **`/users/me` out of scope**
  (Q13). Cleared for the database → implementer → reviewer → security → docs-writer →
  version-control workflow.
