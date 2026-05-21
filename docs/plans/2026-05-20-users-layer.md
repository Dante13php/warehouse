# Users Layer (users table, UserStorage, real UserLookup, user management endpoints)

## Status

`superseded` — replaced by `docs/plans/2026-05-20-users-endpoint.md`, which targets the
current IoC + `BaseController`/`AbstractService`/`AbstractStorage` architecture and was
implemented on 2026-05-21. This file describes a stale pre-IoC design (router-based wiring,
constructor-injected storages, plain-`Exception` errors) and is retained for history only.

## Source task

User request: implement the **Users layer** of the Warehouse project. This is the
follow-up the Auth layer explicitly deferred (see
`docs/plans/2026-05-20-auth-layer.md` "Out of scope": the `users` table, Alembic
migration, seed SQL, and a concrete `UserStorage` were left for "the next step",
with only a `UserLookup` Protocol + `AuthUser` Data + `NotImplementedUserLookup`
stub created).

Concretely this task delivers:

- the `users` table in each `client_{slug}` (per-tenant) database, via an Alembic
  migration in the `client_template` lineage;
- a `User` Data class, with `AuthUser` reconciled against it;
- a `UserStorage` (the only DB-touching layer for users);
- a `UserService` (manager-gated user management business logic);
- a real `UserLookup` implementation backed by `UserStorage`, wired into
  `app/controllers/auth/router.py` to replace `NotImplementedUserLookup`;
- user management endpoints (`/users/me`, `GET/POST /users`, `PATCH /users/{id}`).

The design contract for users is already documented in
`docs/application-stack/auth.md` ("Users and roles": per-tenant `users` table,
bcrypt hashes, `manager`/`staff` roles) and `docs/application-stack/multi-tenancy.md`
(every table has `tenant_id`, every storage query filters by it, RLS as a second
layer). This plan implements that contract.

## Existing code this builds on

| File | Relevance |
|---|---|
| `app/data/auth_user.py` | `AuthUser(id, tenant_id, email, role, password_hash)` + `from_row` — same entity as `User`; must be reconciled (see Decisions). |
| `app/services/auth/user_lookup.py` | `UserLookup` Protocol (`get_by_email(email, db_name) -> AuthUser \| None`) + `NotImplementedUserLookup` stub to replace. |
| `app/services/auth/service.py` | `AuthService` consumes `UserLookup`; reads `user.id/tenant_id/email/role/password_hash`. Must keep working unchanged. |
| `app/controllers/auth/router.py` | `_build_auth_service()` wires `NotImplementedUserLookup()`; passes `db_name=settings.alembic_shared_db`. Both must change. |
| `app/helpers/password.py` | `hash_password` / `verify_password` (passlib bcrypt) — used by `UserService.create_user`. |
| `app/helpers/security.py` | `get_current_user` dependency → `TokenData(sub, tenant_id, role)`. Authn for `/users` endpoints. |
| `app/data/token.py` | `TokenData(sub, tenant_id, role)` from verified JWT claims — source of `user_id`/`tenant_id`/`role` for endpoints. |
| `app/infrastructure/database.py` | `get_db(db_name)` async-session dependency; `get_engine` (NullPool, prepared-stmt cache off for PgBouncer). |
| `app/infrastructure/transaction.py` | `TransactionHelper.wrap(session, func, ...)` — controller wraps mutations. |
| `app/storages/refresh_token_storage.py` | reference storage style (plain class, no base, methods take the backing resource). |
| `alembic/env.py`, `alembic.ini` | multi-DB Alembic; `[client_template]` section → `alembic/versions/client_template/`. Only `.keep` exists there now (no first revision yet). |
| `docker/init-db.sql` | bootstraps `aton_clients` + `client_template` databases; schema applied by Alembic. |

## Scope

### 1. Database — `users` table (per-tenant)

Add a `users` table to the **`client_template`** Alembic lineage (it propagates to
every `client_{slug}` tenant database). Columns exactly as required:

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | server default `gen_random_uuid()` (requires `pgcrypto`) **or** app-generated `uuid4` — see Decision Q3 |
| `tenant_id` | `UUID` NOT NULL | tenant scope; present even though DB is tenant-private (defense in depth) |
| `email` | `CITEXT` or `TEXT` NOT NULL | unique **per tenant** → `UNIQUE (tenant_id, email)` |
| `password_hash` | `TEXT` NOT NULL | bcrypt hash; never logged |
| `role` | enum `user_role` (`manager`, `staff`) | Postgres `ENUM` type, NOT NULL |
| `created_at` | `TIMESTAMPTZ` NOT NULL | server default `now()` |
| `updated_at` | `TIMESTAMPTZ` NOT NULL | server default `now()`; bumped on update (app-side and/or trigger) |

Constraints / indexes (documented access patterns only — no speculative indexes):

- PK on `id`.
- `UNIQUE (tenant_id, email)` — enforces per-tenant email uniqueness **and** backs
  the hot `get_by_email(email, tenant_id)` lookup (no separate index needed).
- `get_by_id` is served by the PK; queries still add `AND tenant_id = :tenant_id`.

RLS (per multi-tenancy rules — second enforcement layer):

- `ALTER TABLE users ENABLE ROW LEVEL SECURITY;`
- A tenant-isolation policy keyed off a session-scoped tenant setting
  (e.g. `current_setting('app.tenant_id')`). **Note:** nothing in the codebase
  sets that GUC today, so an over-restrictive policy would break all queries. See
  Decision Q5 — propose `ENABLE RLS` + a policy that is correct once the tenant
  GUC is wired, but confirm whether to set the GUC now (in `get_db`/session
  setup) or defer the policy enforcement to a later task and ship `ENABLE RLS`
  with a permissive-for-now policy. The database/security agents own this call.

Migration:

- New file under `alembic/versions/client_template/` (this is the **first**
  revision in that lineage; `down_revision = None`). Filename auto-generated by the
  configured `file_template`; generate via `alembic -n client_template revision -m "create users table"`.
- `upgrade()`: create the `user_role` enum, create `users`, add unique constraint,
  enable RLS + policy, (optionally) `CREATE EXTENSION IF NOT EXISTS pgcrypto`
  and/or `citext` depending on Q3/Q4.
- `downgrade()`: drop `users`, drop the `user_role` enum (and policy).

### 2. Seed SQL — `warehouse_full_seed.sql`

RULES.md: "New tables require `warehouse_full_seed.sql` updates with schema and
seed data." This file **does not exist yet** in the repo. See Decision Q6:
recommended — create `warehouse_full_seed.sql` (at repo root or `docker/`) with the
`users` table schema + at least one seed manager per tenant (bcrypt-hashed
placeholder password, clearly marked dev-only). If the user wants seed handling
deferred or located elsewhere, the database agent adjusts. Either way the plan must
not silently skip this RULES requirement.

### 3. Data layer

`app/data/user.py` — `User` dataclass (fields match DB columns exactly):

```
@dataclass
class User:
    id: str
    tenant_id: str
    email: str
    password_hash: str
    role: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row) -> "User": ...
```

- `@classmethod from_row` factory only; no other logic (Data-layer rule).
- `id`/`tenant_id` stringified in `from_row` (matches `AuthUser.from_row`
  convention of `str(row.id)`).

**`AuthUser` reconciliation** (required by task). `AuthUser` and `User` describe
the same entity. `AuthUser` lacks `created_at`/`updated_at`; `AuthService` only
reads `id`, `tenant_id`, `email`, `role`, `password_hash`. Options (Decision Q1):

- **(A, recommended)** Make `User` the single canonical Data class and **delete**
  `AuthUser`. `UserLookup` Protocol return type changes to `User | None`;
  `AuthService` keeps working (it only touches the shared subset). Fewest moving
  parts, no duplicate entity (RULES anti-pattern: don't keep two entities for one
  thing).
- **(B)** Keep `AuthUser` as a narrow auth-only projection and have the real
  `UserLookup` build an `AuthUser` from a `User` row. More indirection, two
  classes for one entity.

Recommend **A**. The reconciliation work under A:
- update `app/services/auth/user_lookup.py` Protocol signature to `User`,
- update the `AuthService` type imports if any reference `AuthUser`,
- remove `app/data/auth_user.py` (and its import in the auth-layer "what was built"
  note is historical only — no code import remains).

### 4. Storage layer

`app/storages/user_storage.py` — `UserStorage` (the only users DB-access layer).
Plain class (matches `RefreshTokenStorage` style; no Manager/Repository base —
RULES anti-pattern). All methods are `async`, take a SQLAlchemy `AsyncSession`,
**filter every query by `tenant_id`**, never start a transaction, and return
`User` / `list[User]` / `None` only.

| Method | Signature | Behavior |
|---|---|---|
| `get_by_email` | `(email: str, tenant_id: str, session: AsyncSession) -> User \| None` | `SELECT ... WHERE tenant_id = :tid AND email = :email`; `User.from_row` or `None`. |
| `get_by_id` | `(id: str, tenant_id: str, session: AsyncSession) -> User \| None` | `SELECT ... WHERE tenant_id = :tid AND id = :id`. |
| `create` | `(user: User, session: AsyncSession) -> User` | `INSERT`; assign generated `id`/`created_at`/`updated_at` back onto the passed `user` (Storage rule: assign generated PK back), `RETURNING` columns. |
| `update` | `(user: User, session: AsyncSession) -> User` | `UPDATE ... WHERE tenant_id AND id`; bump `updated_at`; `RETURNING`. |
| `list` | `(tenant_id: str, session: AsyncSession) -> list[User]` | `SELECT ... WHERE tenant_id = :tid ORDER BY created_at` (stable order). |

- Use SQLAlchemy Core (`text()` or `sqlalchemy.table/column` constructs) for these
  queries (no ORM models exist in the project; storages are query-based). Consistent
  with the Core-for-queries guidance in RULES.
- `email` comparison must respect the per-tenant uniqueness semantics chosen in Q4
  (CITEXT vs lower()-normalized).

### 5. Service layer

`app/services/users/service.py` — `UserService`. Constructor-injected
`UserStorage` (DI, not service locator). All business logic here; never starts a
transaction; never touches the DB directly. `db_name` is threaded through so the
service can open the correct tenant session if needed (see Decision Q2 on whether
the service receives a `session` or a `db_name`).

Authorization is **manager-only** for create/update/list. The role comes from the
verified `TokenData.role` (never request input). Decision Q7: where the role check
lives — recommended a `require_manager` check at the controller boundary (a small
FastAPI dependency reading `get_current_user`), **and** a defensive role check in
the service that raises a `ForbiddenError`. Controller dependency gives the clean
403; the service check is defense-in-depth.

| Method | Signature (proposed) | Logic |
|---|---|---|
| `get_me` | `(user_id: str, tenant_id: str, db_name: str, session) -> User` | load self via `get_by_id`; raise `UserNotFoundError` if `None`. Any authenticated role. |
| `create_user` | `(email, password, role, tenant_id, db_name, session) -> User` | manager only. Check no existing user with that email (`get_by_email`) → raise `UserAlreadyExistsError`. `hash_password(password)`. Build `User` (new `tenant_id` = caller's). `storage.create`. Return created user. |
| `update_user` | `(user_id, fields: dict, tenant_id, db_name, session) -> User` | manager only. Load target via `get_by_id` (scoped to tenant) → `UserNotFoundError` if missing. Apply only submitted fields (`email`, `password`→hash, `role`); if `email` changes, re-check uniqueness. `storage.update`. |
| `list_users` | `(tenant_id, db_name, session) -> list[User]` | manager only. `storage.list`. |

The exact parameter shape (passing `session` in vs the service opening one from
`db_name`) is Decision Q2. The task signature lists both `db_name` and the storage
methods take `session`; recommended the controller opens the session
(`Depends(get_db(db_name))`-style) and passes it down, with `db_name` retained for
logging/future routing — matching how `AuthService` already receives `db_name`.

`hash_password` from `app/helpers/password.py` is used **only** in
`create_user` and in `update_user` when a new password is submitted. Plaintext
passwords are never logged.

### 6. Auth integration — real `UserLookup`

Replace `NotImplementedUserLookup` with a real implementation backed by
`UserStorage`. Two sub-problems:

1. **Signature mismatch.** The Protocol is `get_by_email(email, db_name)` but
   `UserStorage.get_by_email` needs `(email, tenant_id, session)`. The real lookup
   must (a) open an async session for `db_name` via `get_session(db_name)` /
   `get_db`, and (b) supply a `tenant_id`. At login time there is **no JWT yet**, so
   `tenant_id` is not available from claims.

   This exposes a **pre-existing architectural gap**: `auth/router.py` currently
   passes `db_name=settings.alembic_shared_db` (`aton_clients`), but users live in
   `client_{slug}` tenant databases (multi-tenancy.md). Login cannot resolve a
   tenant DB or a `tenant_id` from email alone without a tenant lookup. Decision Q8
   resolves this. Options:
   - **(B1, recommended for this task's stated scope)** Implement the real
     `UserLookup` against a session, and have it derive `tenant_id` from the row
     itself: query `users` by `email` within a given tenant DB; `get_by_email` in a
     **single-tenant / template** context where `db_name` already identifies the
     tenant DB and the query filters by the `tenant_id` stored on the row. Since the
     DB is tenant-private, "by email" within that DB is unambiguous. The real lookup
     does: open session for `db_name` → `SELECT ... WHERE email = :email` (DB is
     tenant-private) → return `User`. It still passes the row's `tenant_id` through.

     To honor the "every storage query filters by tenant_id" rule, the lookup path
     needs a `tenant_id`. Cleanest: add a storage method or allow `get_by_email`'s
     `tenant_id` to be resolved from a tenant registry before the call. For the
     scope here, recommended: the real `UserLookup` resolves `db_name` →
     `tenant_id` is not yet derivable, so login keeps using a single configured
     tenant DB until the **tenant-routing task** lands.
   - **(B2)** Full tenant routing (email → tenant via `aton_clients` registry →
     `db_name` + `tenant_id`) — larger, arguably a separate task (the auth plan
     listed tenant DB routing as out of scope).

   **Recommendation:** keep this task focused on users CRUD + a real `UserLookup`
   that works against a **given tenant DB session**, and explicitly call tenant
   routing (email→tenant resolution) a follow-up. The real `UserLookup` will:
   - accept `db_name`, open a session via `get_session(db_name)`,
   - run a `UserStorage`-backed query for the user by email,
   - return a `User` (option A) the `AuthService` can consume.

   The `tenant_id`-filter rule is satisfied because the user row carries
   `tenant_id` and the storage query for this private DB can filter by it once known
   (or, until routing lands, the DB-per-tenant boundary is the isolation). This
   nuance is flagged for the security + database agents at approval.

2. **Wiring.** Update `app/controllers/auth/router.py`:
   - `_build_auth_service()` injects `RealUserLookup(UserStorage())` instead of
     `NotImplementedUserLookup()`.
   - revisit the `db_name=settings.alembic_shared_db` argument in `login` (Q8): it
     should point at a tenant DB, not the registry; until routing lands, document
     the chosen interim value.

New file: `app/services/auth/user_lookup.py` gains the real class (or a new
`app/storages`/`app/services/auth/real_user_lookup.py`). Recommended: keep it in
`user_lookup.py` next to the Protocol.

### 7. Requests

`app/requests/users/create_user.py` — `CreateUserRequest`:
- `email: EmailStr` (normalized: trim + lowercase),
- `password: str` (min length policy — Decision Q9, propose ≥ 8),
- `role: Literal["manager", "staff"]` (validated against the role enum).

`app/requests/users/update_user.py` — `UpdateUserRequest` (PATCH semantics):
- all fields optional: `email`, `password`, `role`;
- validate **only submitted fields** using `model_fields_set` (RULES PATCH rule);
- expose which fields were set so the service applies only those (e.g. via
  `request.model_dump(exclude_unset=True)`).

Both follow the existing Pydantic `BaseModel` style (`LoginRequest` precedent) and
do all validation at the boundary; downstream trusts validated input.

### 8. Controllers / Endpoints

`app/controllers/users/router.py` — `APIRouter(prefix="/users", tags=["users"])`,
registered in `app/main.py`. Controllers: no business logic, no DB access, lazy
service resolution, wrap mutations in `TransactionHelper.wrap`.

| Method | Path | Auth | Body | Returns |
|---|---|---|---|---|
| `GET` | `/users/me` | any authenticated (`get_current_user`) | — | current `User` (response model excludes `password_hash`) |
| `GET` | `/users` | manager only | — | `list[User]` (sans `password_hash`) |
| `POST` | `/users` | manager only | `CreateUserRequest` | created `User`, 201 |
| `PATCH` | `/users/{user_id}` | manager only | `UpdateUserRequest` | updated `User` |

- `user_id` / `tenant_id` for `get_me` come from `TokenData` (verified claims),
  never request input.
- Mutations (`POST`, `PATCH`) wrapped via `transaction_helper.wrap(session, ...)`.
- A **response model** (e.g. `UserResponse` Pydantic model, or a serializer) must
  strip `password_hash` so it is never returned. Decision Q10: add a `UserResponse`
  response schema (recommended) vs hand-built dict. Recommended `UserResponse`.
- `created_at`/`updated_at` serialized as ISO 8601 UTC (`...Z`) per RULES.
- Manager gate via a `require_manager` dependency (built on `get_current_user`),
  returning 403 for `staff`.

### 9. Errors

`app/errors/users/errors.py` — domain errors. The auth layer chose **plain
`Exception` subclasses** (no `ApplicationError`/`ErrorDefinitions` base was created
— see auth plan decision 5). Follow that reality (Decision Q11): plain exceptions
now, mapped to HTTP in the controller, with unique error codes/messages.

| Error | Maps to | When |
|---|---|---|
| `UserNotFoundError` | 404 | `get_me`/`update_user` target missing |
| `UserAlreadyExistsError` | 409 | create/update with a taken email (also caught from the unique constraint) |
| `ForbiddenError` (or reuse a shared one) | 403 | non-manager calling a manager-only method (defense-in-depth) |

Controller maps these to `HTTPException` (mirrors how `auth/router.py` maps
`InvalidCredentialsError` → 401). If the user prefers introducing the shared
`ApplicationError` base now, that is a larger cross-cutting change — flag, don't
assume.

### 10. main.py

Register `users_router` alongside `auth_router` in `app/main.py`.

## Out of scope

- **Tenant DB routing / email→tenant resolution** (resolving `tenant_id` and
  `client_{slug}` `db_name` from the registry at login). The real `UserLookup` here
  works against a given tenant DB session; full routing remains the deferred task
  the auth plan named. (Decision Q8 may pull a minimal slice in — confirm at
  approval.)
- **Self-service registration / signup** endpoint (users are created by a manager).
- **Password reset / email verification / change-own-password** flows.
- **User deletion / deactivation** (`DELETE /users/{id}`, soft-delete, `is_active`).
  Not in the required column set or endpoint list.
- **Pagination / filtering / search** on `GET /users` (return full tenant list;
  add later if access patterns demand — no speculative work).
- **Rate limiting** on user endpoints.
- **Fanning the migration out to every live `client_{slug}` DB** (the multi-DB
  runner / provisioning loop) — this task adds the revision to the `client_template`
  lineage; running it across existing tenants is the provisioning task.
- **Frontend / UI** for user management.
- Introducing a shared `ApplicationError`/`ErrorDefinitions` base (unless approved
  under Q11).

## Acceptance criteria

- Alembic `client_template` revision creates `users` with all required columns,
  the `user_role` enum (`manager`/`staff`), `UNIQUE (tenant_id, email)`, and RLS
  enabled; `upgrade`/`downgrade` are symmetric.
- `alembic -n client_template upgrade head` applies the revision against
  `client_template` (verifiable with the Docker stack; structural correctness
  verified regardless).
- `User` dataclass field names match the DB columns exactly; `from_row` builds a
  `User` from a result row; no other methods.
- `AuthUser` is reconciled per the approved option (recommended: removed; `User` is
  canonical) and `AuthService` still compiles and behaves identically.
- `UserStorage` exposes `get_by_email`, `get_by_id`, `create`, `update`, `list`;
  **every** query includes a `tenant_id` filter; `create` assigns generated
  `id`/timestamps back onto the passed `User`; methods return only `User`/`list[User]`/`None`;
  no transaction is started inside storage.
- `UserService` enforces manager-only on `create_user`/`update_user`/`list_users`;
  `get_me` works for any authenticated role; `create_user` rejects duplicate emails;
  `update_user` applies only submitted fields and re-checks email uniqueness on
  change; passwords are bcrypt-hashed via `hash_password`; the service starts no
  transactions and never touches the DB directly.
- A real `UserLookup` backed by `UserStorage` replaces `NotImplementedUserLookup`
  in `auth/router.py`; `AuthService.login` no longer raises `NotImplementedError`
  for the wired path.
- `CreateUserRequest` validates `email`/`password`/`role`; `UpdateUserRequest`
  validates only submitted fields (`model_fields_set`/`exclude_unset`).
- Endpoints behave per the table: `GET /users/me` returns the caller; `GET /users`,
  `POST /users`, `PATCH /users/{id}` are 403 for `staff`; `POST` returns 201;
  responses **never include `password_hash`**; timestamps are ISO 8601 UTC.
- `tenant_id` and `role` are read only from verified `TokenData` claims — never from
  request body/query/path.
- All new code: full type hints, `logging` not `print`, no mutable default args,
  layer boundaries respected.
- `python -c "import app.main"` imports cleanly with both routers registered.
- `warehouse_full_seed.sql` updated/created with the `users` schema + seed (per
  RULES) unless explicitly deferred at approval.

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `alembic/versions/client_template/<rev>_create_users_table.py` | created (first `client_template` revision) | database |
| `warehouse_full_seed.sql` | created/updated (schema + seed) | database |
| `docker/init-db.sql` | updated only if `pgcrypto`/`citext` extension bootstrap is needed | database |
| `app/data/user.py` | created (`User` + `from_row`) | implementer |
| `app/data/auth_user.py` | removed (option A) or kept as projection (option B) | implementer |
| `app/storages/user_storage.py` | created (`UserStorage`) | implementer |
| `app/services/users/__init__.py` | created | implementer |
| `app/services/users/service.py` | created (`UserService`) | implementer |
| `app/services/auth/user_lookup.py` | updated (real `UserLookup`; Protocol return type → `User`) | implementer |
| `app/services/auth/service.py` | updated only if it imports `AuthUser` (type ref) | implementer |
| `app/controllers/auth/router.py` | updated (`_build_auth_service` wiring + `db_name` arg) | implementer |
| `app/requests/users/__init__.py` | created | implementer |
| `app/requests/users/create_user.py` | created (`CreateUserRequest`) | implementer |
| `app/requests/users/update_user.py` | created (`UpdateUserRequest`) | implementer |
| `app/controllers/users/__init__.py` | created | implementer |
| `app/controllers/users/router.py` | created (`/users` router) | implementer |
| `app/controllers/users/responses.py` (or `app/data`) | created (`UserResponse`, strips `password_hash`) | implementer |
| `app/errors/users/__init__.py` | created | implementer |
| `app/errors/users/errors.py` | created (`UserNotFoundError`, `UserAlreadyExistsError`, `ForbiddenError`) | implementer |
| `app/helpers/security.py` | updated (add `require_manager` dependency) | implementer |
| `app/main.py` | updated (register `users_router`) | implementer |
| `docs/application-stack/auth.md` | updated (users table now implemented; status note) | docs-writer |
| `docs/api/ENDPOINTS.md` | created/updated with the `/users` contracts (file does not exist yet) | docs-writer |
| `docs/plans/2026-05-20-users-layer.md` | status → `implemented` + "What was built" after build | docs-writer |

## Risks

- **`AuthUser` reconciliation breakage.** Changing the `UserLookup` return type and
  removing `AuthUser` touches the working auth path. Mitigation: `AuthService` only
  reads the shared subset (`id`, `tenant_id`, `email`, `role`, `password_hash`);
  `User` is a superset, so the swap is source-compatible. Reviewer must confirm no
  other importer of `AuthUser` remains.
- **Login tenant-routing gap.** `auth/router.py` passes the **registry** DB
  (`aton_clients`) as `db_name`, but users live in `client_{slug}` DBs. A real
  `UserLookup` cannot fully resolve tenant + DB from email alone without registry
  routing, which the auth plan deferred. Risk: end-to-end login still cannot run
  cross-tenant until routing lands. Mitigation: ship a real lookup that works
  against a given tenant DB session and explicitly scope routing out (Q8); call it
  out so the security agent reviews the interim trust boundary.
- **RLS policy vs missing tenant GUC.** Enabling RLS with a policy that reads
  `current_setting('app.tenant_id')` will reject all rows if that GUC is never set
  (nothing sets it today). Risk: every query silently returns 0 rows. Mitigation
  (Q5): coordinate with the database agent — either set the GUC per session in
  `get_db`/session setup as part of this task, or ship `ENABLE RLS` with a
  permissive-now policy and enforce in the routing task. Must be decided before the
  migration is written.
- **PgBouncer transaction pooling + `SET`/GUC.** If the RLS GUC is set per session,
  transaction-mode pooling can leak/clear it across pooled transactions. Use
  `SET LOCAL` inside the transaction, or set it via connection-level config.
  Reviewer/database to verify.
- **UUID generation source.** Server-side `gen_random_uuid()` needs `pgcrypto`;
  app-side `uuid4` avoids the extension but means `create` generates the id before
  insert. Decide consistently (Q3) so `from_row`/`create` agree.
- **Email uniqueness semantics.** Case sensitivity: `Foo@x.com` vs `foo@x.com`.
  `CITEXT` (extension) vs storing lowercased `TEXT` + normalizing in the request
  layer. Mismatch between request normalization and the DB unique index could allow
  duplicates or block legitimate logins (login email must be normalized the same
  way). Decide once (Q4) and apply in request + storage + migration consistently.
- **`password_hash` leakage.** The `User` Data class carries `password_hash`; if a
  controller returns `User` directly it leaks. Mitigation: mandatory `UserResponse`
  that omits it; reviewer/security must confirm no endpoint serializes the raw
  `User`/`password_hash`, and that it is never logged.
- **`warehouse_full_seed.sql` does not exist.** RULES requires updating it, but
  there is no file. Creating it (location, content, seed credentials) needs a
  decision (Q6); a seeded manager with a known dev password is a security note
  (must be dev-only / clearly flagged).
- **Manager-gate placement.** If the role check lives only in the controller, a
  future internal caller could bypass it; if only in the service, the HTTP 403 is
  less clean. Mitigation: both (controller dependency + service guard).
- **No live DB/Redis in CI.** Runtime verification limited to imports + unit-level
  behavior unless the Docker stack is started for an integration check.

## Agent decisions

- **planner**: this plan (no code written).
- **database**: **required.** Owns the `users` migration (first `client_template`
  revision), the `user_role` enum, the `UNIQUE (tenant_id, email)` constraint, RLS
  policy + the GUC decision (Q5), the UUID/email-extension decisions (Q3/Q4), and
  `warehouse_full_seed.sql` (Q6). Must confirm the migration is symmetric and that
  RLS does not silently break reads.
- **ui-designer**: not required (no UI scope).
- **implementer**: owns all `app/` files in the table — `User` Data, `UserStorage`,
  `UserService`, real `UserLookup` + auth wiring, requests, controller/responses,
  errors, `require_manager`, `main.py` registration, and the `AuthUser`
  reconciliation.
- **reviewer**: verify layer boundaries (controller no logic/DB, service no
  transactions/DB, storage only DB + always `tenant_id`-filtered, Data has only
  `from_row`); PATCH validates only submitted fields; `password_hash` never
  returned/logged; manager gate enforced; `tenant_id`/`role` only from claims;
  type hints; no `print`; `AuthUser` swap leaves no dangling imports.
- **security**: **required** (auth path change, multi-tenant isolation, password
  handling, trust boundary). Run after reviewer. Focus: real `UserLookup` tenant
  scoping + the login routing gap (Q8), RLS correctness, per-tenant email
  uniqueness vs enumeration, `password_hash` non-leakage, manager-only
  authorization (no privilege escalation via request-supplied `role`/`tenant_id`),
  seed credential exposure (Q6).
- **docs-writer**: update `docs/application-stack/auth.md` status (users table /
  user endpoints now implemented), create/update `docs/api/ENDPOINTS.md` with the
  `/users` contracts, and set this plan to `implemented` with a "What was built"
  section.
- **spec-writer**: write a plain-language description of user management (a manager
  can create/list/update users; roles are manager/staff; everyone can view their
  own profile) — user-facing functionality is introduced.
- **version-control**: commit the plan + migration + code + doc updates together at
  the end.

## Open questions for approval

1. **`AuthUser` reconciliation**: make `User` canonical and **remove** `AuthUser`
   (recommended, option A), or keep `AuthUser` as an auth-only projection (option B)?
2. **Service parameter shape**: controller opens the `AsyncSession` (via
   `get_db(db_name)`) and passes `session` down, with `db_name` kept for
   logging/future routing (recommended, mirrors `AuthService`) — confirm vs the
   service opening its own session from `db_name`.
3. **UUID generation**: Postgres `gen_random_uuid()` (needs `pgcrypto`) vs app-side
   `uuid4` in `UserStorage.create`? (Recommended: app-side `uuid4` — no extension
   dependency, consistent with stringified ids in `from_row`.)
4. **Email column type / case handling**: `CITEXT` (needs extension) vs `TEXT` with
   lowercase normalization in the request layer + `UNIQUE (tenant_id, lower(email))`?
   (Recommended: `TEXT` + normalize-on-input, normalize login email the same way.)
5. **RLS now or later**: enable RLS with a real `current_setting('app.tenant_id')`
   policy **and wire the GUC** in this task, or `ENABLE RLS` with a permissive
   policy and defer GUC enforcement to the tenant-routing task? (Recommended: ship
   `ENABLE RLS` now; enforce GUC when routing lands, to avoid silently empty reads.)
6. **`warehouse_full_seed.sql`**: create it now (recommended; root or `docker/`)
   with `users` schema + a dev-only seed manager, or defer seed handling? Confirm
   location and whether a seed user is wanted.
7. **Manager-gate placement**: controller `require_manager` dependency **and**
   service-level role guard (recommended), or one of the two?
8. **Login tenant routing**: keep email→tenant routing **out of scope** and ship a
   real `UserLookup` that works against a given tenant DB session (recommended), or
   pull minimal registry-driven routing into this task? Confirm what interim
   `db_name` `login` should use (currently `aton_clients`).
9. **Password policy**: minimum length / rules for `CreateUserRequest` /
   `UpdateUserRequest` (recommended: ≥ 8 chars, no other hard rules).
10. **Response shape**: add a dedicated `UserResponse` model that omits
    `password_hash` (recommended) vs hand-built dicts in the controller.
11. **Errors base**: keep plain `Exception` subclasses mapped in the controller
    (recommended, matches the auth layer), or introduce the shared
    `ApplicationError`/`ErrorDefinitions` base now (larger change)?

## Approval log

- 2026-05-20: plan drafted, status `draft`. For a future implementation session.
  The eleven open questions above must be resolved (or recommended defaults
  accepted) before implementation starts. No approval recorded yet.
