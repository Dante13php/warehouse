# Auth Layer (JWT access + Redis refresh + middleware)

## Status

`implemented`

## What was built

All files listed in the approved plan were created on 2026-05-20:

- `app/infrastructure/settings.py` — added `refresh_token_expire_days: int = 7`
- `app/data/token.py` — `TokenData` dataclass (`sub`, `tenant_id`, `role`)
- `app/data/auth_user.py` — `AuthUser` dataclass (`id`, `tenant_id`, `role`, `hashed_password`)
- `app/helpers/jwt.py` — `create_access_token` / `decode_access_token` using `python-jose`
- `app/helpers/security.py` — `get_current_user` FastAPI dependency with `OAuth2PasswordBearer`
- `app/storages/refresh_token_storage.py` — `RefreshTokenStorage` with `save`, `get_user_id`, `delete`; Redis key `refresh:{token}`
- `app/services/auth/__init__.py` — empty
- `app/services/auth/service.py` — `UserLookup` Protocol, `NotImplementedUserLookup` stub, `AuthService` with `login` (timing-safe bcrypt), `refresh` (rotation), `logout` (idempotent)
- `app/requests/auth/__init__.py` — empty
- `app/requests/auth/login.py` — `LoginRequest` (EmailStr + password)
- `app/requests/auth/refresh.py` — `RefreshRequest` (refresh_token)
- `app/controllers/auth/__init__.py` — empty
- `app/controllers/auth/router.py` — `APIRouter(prefix="/auth")` with `POST /login`, `POST /refresh`, `POST /logout (204)`
- `app/errors/auth/__init__.py` — empty
- `app/errors/auth/errors.py` — `InvalidCredentialsError`, `TokenExpiredError`, `InvalidTokenError`
- `app/main.py` — registered `auth_router`

Decisions applied from approval:
- No `app/errors/base.py` created (per approved answer 5)
- Logout returns `204 No Content` (per approved answer 4)
- Timing-safe dummy bcrypt verify for unknown users implemented (per approved answer 3)
- `refresh_token_expire_days = 7` setting added (per approved answer 2)
- No new dependencies added — `python-jose` and `passlib[bcrypt]` were already in `pyproject.toml` (per approved answer 1)

## Source task

User request: implement the Auth layer of the Warehouse project — stateless JWT
access tokens, Redis-backed revocable refresh tokens, and an auth middleware /
dependency that verifies the access token and produces a trusted identity object.

Existing infrastructure to build on:
- `app/infrastructure/settings.py` — `jwt_secret_key`, `jwt_algorithm`, `jwt_access_token_expire_minutes`
- `app/infrastructure/redis.py` — `get_redis()` dependency (`Redis`, `decode_responses=True`)
- `app/infrastructure/database.py` — `get_db(db_name)` dependency
- `app/infrastructure/transaction.py` — `TransactionHelper`
- `app/main.py` — `app = FastAPI(title="Warehouse")`

The design contract is already documented in `docs/application-stack/auth.md`
(token claims, login / refresh / logout flows, rotation, bcrypt). This plan
implements that contract for the parts in scope.

## Scope

Implement the auth feature across the standard layers, plus two helpers and a
shared error base. Concretely:

### Endpoints (`app/controllers/auth/`)
- `POST /auth/login` — `{ email, password }` -> `{ access_token, refresh_token, token_type }`
- `POST /auth/refresh` — `{ refresh_token }` -> new `{ access_token, refresh_token, token_type }` (rotation)
- `POST /auth/logout` — `{ refresh_token }` -> 204 / `{ status }`; revokes the refresh token in Redis

### Requests (`app/requests/auth/`)
- `LoginRequest` — validates/normalizes `email` (lowercase, trim, format) and `password` (non-empty)
- `RefreshRequest` — validates `refresh_token` (non-empty string)
- `LogoutRequest` — validates `refresh_token` (non-empty string)

### Service (`app/services/auth/auth_service.py`)
- `AuthService` with `login`, `refresh`, `logout`.
- `login`: look up user via the **user-lookup interface** (see below), verify bcrypt
  password, mint access JWT, create + store refresh token in Redis, return token pair.
- `refresh`: look up refresh token in Redis, validate not revoked/expired, **rotate**
  (delete old, store new), mint new access JWT, return new pair.
- `logout`: delete the refresh token key in Redis (idempotent).
- Never starts transactions; never touches the DB directly; uses storages/helpers.

### User-lookup placeholder/interface
- `users` table and a concrete `UserStorage` are **out of scope** (next step).
- Define an abstract interface `UserLookup` (Python `Protocol` or ABC) in
  `app/services/auth/user_lookup.py` with a single method:
  `async def get_by_email(self, email: str) -> AuthUser | None`.
- Define a minimal `AuthUser` `Data` dataclass (`app/data/auth_user.py`) carrying the
  fields auth needs: `id`, `tenant_id`, `email`, `password_hash`, `role`.
- `AuthService.__init__` receives a `UserLookup` (constructor injection). Provide a
  `NotImplementedUserLookup` stub (raises `NotImplementedError` / a clear AuthError)
  so the wiring is complete and the next task only swaps in the real `UserStorage`.

### Data (`app/data/`)
- `token.py` — `TokenData` dataclass: `sub`, `tenant_id`, `role`. `from_row` not
  applicable (built from JWT claims); provide a `from_claims` classmethod factory.
- `auth_user.py` — `AuthUser` dataclass (see above) with `from_row` classmethod.

### Refresh-token storage (`app/storages/refresh_token_storage.py`)
- `RefreshTokenStorage` wraps Redis access for refresh tokens (the only place that
  touches Redis for this feature). Methods: `store(token, sub, tenant_id, role, ttl)`,
  `get(token) -> stored claims | None`, `revoke(token)`.
- Stores the claims needed to mint a new access token on refresh (sub, tenant_id, role).
- Key namespace: `refresh:{token}`; value: JSON of claims; TTL set from a configured
  refresh lifetime.

### Helpers
- `app/helpers/jwt.py`
  - `create_access_token(sub, tenant_id, role) -> str` — signs `{sub, tenant_id, role, exp}`
    using `jwt_secret_key` / `jwt_algorithm`, `exp = now + jwt_access_token_expire_minutes`.
  - `decode_access_token(token) -> dict` — verifies signature + expiry, returns claims;
    raises on invalid/expired.
- `app/helpers/password.py` — bcrypt `hash_password` / `verify_password` (passlib or bcrypt).
- `app/helpers/security.py`
  - `get_current_user` FastAPI dependency: reads `Authorization: Bearer <jwt>`,
    decodes/verifies via `decode_access_token`, returns `TokenData(sub, tenant_id, role)`.
  - Uses `fastapi.security.HTTPBearer` for the scheme; raises 401 on missing/invalid token.

### Errors (`app/errors/`)
- `app/errors/base.py` — `ApplicationError` base + `ErrorDefinitions` (does not exist yet;
  RULES references it). Minimal, shared, so the auth domain and future domains extend it.
- `app/errors/auth/` — `AuthError` subclasses with unique codes:
  `InvalidCredentialsError`, `InvalidTokenError`, `ExpiredTokenError`,
  `RefreshTokenNotFoundError` (+ map to HTTP 401 in controller / exception handler).

### Wiring
- Register the auth router on `app` in `app/main.py`.
- Register an exception handler (or per-route handling) that maps `ApplicationError`
  subclasses to HTTP responses with the error code, without leaking internals.

## Out of scope

- `users` table, Alembic migration, seed SQL, and concrete `UserStorage` (next task).
  This plan only defines the `UserLookup` interface + `AuthUser` Data + a stub.
- Tenant DB routing (resolving `tenant_id` -> `db_name`). `login` here assumes a
  single-DB or injected lookup; cross-tenant DB routing is a separate concern.
- Rate limiting on `/auth/login` (Redis-based) — note as a follow-up, not built here.
- Role-based authorization dependency (e.g. `require_role`) — only authentication
  (`get_current_user`) is in scope; authorization helpers are a later task.
- Email verification, password reset, registration endpoints.
- Frontend / UI work.

## Acceptance criteria

- `create_access_token` produces a JWT with exactly `sub`, `tenant_id`, `role`, `exp`;
  `decode_access_token` round-trips it and rejects tampered/expired tokens.
- `get_current_user` returns a `TokenData(sub, tenant_id, role)` for a valid
  `Authorization: Bearer` token and raises 401 for missing/malformed/expired/invalid tokens.
- `POST /auth/login` with valid credentials returns an access token + refresh token;
  with bad credentials returns 401 `InvalidCredentialsError` (same response for unknown
  email vs wrong password — no user enumeration).
- The refresh token is an opaque UUID (not a JWT), stored in Redis with a TTL, and is
  revocable.
- `POST /auth/refresh` with a valid stored refresh token returns a new access token and a
  **rotated** refresh token; the old refresh token no longer works. Invalid/revoked
  refresh token returns 401.
- `POST /auth/logout` deletes the refresh token from Redis and is idempotent (logging out
  twice does not error).
- `tenant_id` and `role` are only ever read from verified JWT claims or the Redis-stored
  refresh record — never from request body/query.
- Passwords are bcrypt-verified; plaintext passwords are never logged.
- All new code: full type hints, `logging` not `print`, no mutable default args, layers
  respected (controller no logic/DB, service no transactions/DB, Redis only via storage).
- `python -c "import app.main"` imports cleanly with the auth router registered.

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `app/helpers/jwt.py` | created | implementer |
| `app/helpers/password.py` | created | implementer |
| `app/helpers/security.py` | created | implementer |
| `app/data/token.py` | created | implementer |
| `app/data/auth_user.py` | created | implementer |
| `app/storages/refresh_token_storage.py` | created | implementer |
| `app/services/auth/__init__.py` | created | implementer |
| `app/services/auth/auth_service.py` | created | implementer |
| `app/services/auth/user_lookup.py` | created (interface + stub) | implementer |
| `app/requests/auth/__init__.py` | created | implementer |
| `app/requests/auth/login_request.py` | created | implementer |
| `app/requests/auth/refresh_request.py` | created | implementer |
| `app/requests/auth/logout_request.py` | created | implementer |
| `app/controllers/auth/__init__.py` | created | implementer |
| `app/controllers/auth/auth_controller.py` | created (router) | implementer |
| `app/errors/base.py` | created (`ApplicationError`, `ErrorDefinitions`) | implementer |
| `app/errors/auth/__init__.py` | created | implementer |
| `app/errors/auth/auth_errors.py` | created | implementer |
| `app/main.py` | updated (register router + exception handler) | implementer |
| `app/infrastructure/settings.py` | updated (add `refresh_token_expire_days`/seconds) | implementer |
| `.env` | updated (add refresh TTL if a new var is introduced) | implementer |
| `pyproject.toml` / requirements | updated (`pyjwt` + `passlib[bcrypt]` or `bcrypt`) | implementer |

## Risks

- **Dependency choice / install**: JWT (`pyjwt`) and bcrypt (`passlib[bcrypt]` or
  `bcrypt`) are new dependencies. Confirm whether the implementer may add them to
  `pyproject.toml` and whether `pip install` may be run, or whether install is deferred.
- **Secrets**: `jwt_secret_key` must come only from settings/env; it must never be
  logged or returned. Algorithm pinned to `jwt_algorithm` (avoid `alg: none` / alg
  confusion — decode must enforce the configured algorithm).
- **User enumeration**: login must return an identical error for unknown email and wrong
  password, and should run a dummy bcrypt verify for unknown users to avoid timing
  leaks (decide at approval whether timing-safety is in scope or follow-up).
- **Refresh token rotation race**: concurrent refresh with the same token — accept
  last-writer-wins / single-use semantics; documented, not hardened with locks here.
- **`ErrorDefinitions` / `ApplicationError` base does not exist yet**: this task creates
  it. Keep it minimal and generic so it does not pre-constrain future domains.
- **No live Redis/DB in CI**: runtime verification is limited to imports + unit-level
  behavior unless the user wants the Docker stack started for an integration check.
- **Tenant routing gap**: because tenant DB routing is out of scope, `login`'s user
  lookup is via the injected `UserLookup` stub; end-to-end login cannot be exercised
  until the real `UserStorage` lands. This is intentional and called out.

## Agent decisions

- planner: this plan (no code written).
- ui-designer: not required (no UI scope).
- database: not required for this task — no schema/migration here (`users` table is the
  next task and will go through the database agent then).
- implementer: owns all files in the table above, to the contract in this plan.
- reviewer: verify layer boundaries, type hints, no `print`, JWT claim set + algorithm
  pinning, refresh rotation, idempotent logout, no `tenant_id`/`role` from request input.
- security: **required** (auth, secrets, trust boundary). Run after reviewer. Focus:
  alg confusion, secret handling, user enumeration/timing, token rotation/revocation,
  401 error leakage, bearer parsing.
- docs-writer: update `docs/application-stack/auth.md` status note (endpoints/middleware
  now implemented) and set this plan's status to `implemented` with a "What was built"
  section. Update `docs/api/ENDPOINTS.md` if it exists / is in the docs contract.
- spec-writer: write a plain-language description of login/refresh/logout for non-technical
  users (user-facing functionality is introduced).
- version-control: commit plan + code together at the end.

## Open questions for approval

1. May the implementer add `pyjwt` and `passlib[bcrypt]` (or `bcrypt`) to project deps
   and run the install, or should dependency install be deferred?
2. Refresh token TTL: confirm value (proposed default 7 days) and the env/setting name
   (`refresh_token_expire_days`).
3. Is timing-safe login (dummy bcrypt verify for unknown users) in scope now, or a
   follow-up? (Recommended: in scope — it is cheap and closes an enumeration vector.)
4. Logout response: `204 No Content` vs `200 { "status": "ok" }` — preference?
5. Confirm creating the shared `app/errors/base.py` (`ApplicationError` + `ErrorDefinitions`)
   as part of this task, since RULES references it but it does not exist yet.

## Approval log

- 2026-05-20: plan drafted, awaiting user approval. Open questions above must be
  resolved (or accepted as recommended) before implementation starts.
