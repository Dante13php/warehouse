# Auth Middleware + CurrentUserMapper Initialization (JWT + API key)

## Status

`implemented`

## Source task

The user referenced three CloudSale PHP files as a conceptual blueprint:

- **AbstractMapper.php** — base mapper, lazy-loads dependencies from the IoC container.
- **ActiveUserMapper.php** — holds the active user for the request, initialized once
  per request, exposes `getId()`, `getUsername()`, `isEnabled()`, `isWaiter()`,
  `isManager()`, may lazy-load an API key from Storage.
- **BaseController.php** — in its constructor (before any controller method) checks
  whether `ActiveUserMapper` is initialized; if not, inspects the path (API vs Web)
  and initializes the user: `/api/*` reads an API key from the request and looks up
  the user; Web paths read the session and look up the user.

The user wants the **same concept** in the Warehouse Python backend, with these explicit
requirements:

1. No separate auth controller for this initialization.
2. Authentication must happen **before** the controllers — in middleware.
3. In the future, an **API key** per user (for external API clients) will be used.
4. The UI will use a **JWT session** (refresh-token flow — already implemented).
5. Both paths must initialize `CurrentUserMapper` with the user's identity.
6. The concept must be identical: middleware / before-controller logic initializes the
   mapper; controllers only read from it.
7. Fix documentation / MD files where needed at the end.

## Current state (verified by reading the code)

- `app/infrastructure/ioc.py` — `Ioc` already carries `claims: TokenData | None` and
  `tenant_id`. **Today the JWT is decoded inside the `get_ioc` dependency**, not in
  middleware. `get_ioc` builds the container with `session=None` and `token_data` from
  an optional bearer token. This is a FastAPI dependency, not middleware, so it does not
  satisfy requirement #2 ("auth must happen before controllers, in middleware").
- `app/mappers/abstract_mapper.py` — `AbstractMapper`, the Python equivalent of
  `AbstractMapper.php` (lazy IoC access via `self.X`). Already correct, no change needed.
- `app/mappers/current_user_mapper.py` — `CurrentUserMapper`, the Python equivalent of
  `ActiveUserMapper.php`. Reads identity from `self._ioc.claims`. Has `is_initialized()`,
  `user_id`, `tenant_id`, `role`, `is_admin()`, `is_manager()`. Identity properties raise
  `UnauthenticatedError` when claims are absent. Has a documented extension point for
  lazy profile loading but no API-key support yet.
- `app/controllers/base_controller.py` — `BaseController` holds the single
  `Depends(get_ioc)` and delegates `self.X` to the container. It does **not** perform the
  "init the mapper if not initialized" check that `BaseController.php` does — by design,
  because the user wants that in middleware, not the controller.
- `app/helpers/security.py` — `get_current_user` dependency decodes the bearer token and
  raises 401 on failure. This is the per-route auth gate for protected routes.
- `app/services/auth/auth_service.py` + `not_implemented_user_lookup_service.py` —
  login/refresh/logout work; the user lookup is a `NotImplementedError` stub
  (no `users` table yet).
- `app/storages/refresh_token_storage.py` — Redis-backed refresh tokens. No API-key
  storage exists.
- `app/data/token.py` — `TokenData(sub, tenant_id, role)`; `app/data/auth_user.py` —
  `AuthUser(id, tenant_id, email, role, password_hash)`.

### Key architectural finding

The container **already** receives verified claims, but the **timing and location** are
wrong relative to the user's request. The work is primarily about **moving JWT verification
out of the `get_ioc` dependency into a real ASGI/HTTP middleware that runs before any
controller**, and giving that middleware a **second strategy (API key)** that resolves a
user and seeds identity onto the request — mirroring the PHP `BaseController` path
inspection, but relocated to middleware per requirement #2.

## Scope

A middleware-driven identity-initialization layer with two pluggable strategies, feeding a
single `CurrentUserMapper`, while keeping controllers free of auth logic.

### 1. Authentication middleware (new) — `app/infrastructure/auth_middleware.py`

A FastAPI/Starlette `BaseHTTPMiddleware` (or pure ASGI middleware) registered in
`app/main.py` that runs before route handlers. Per request it:

1. Attempts **JWT bearer** authentication: read `Authorization: Bearer <jwt>`, decode via
   `decode_access_token`. On success, attach the resulting `TokenData` to
   `request.state.token_data`.
2. If no valid JWT, attempts **API-key** authentication: read the configured API-key header
   (e.g. `X-API-Key`), resolve it to a user via an `ApiKeyStorage` lookup. On success,
   build a `TokenData` (sub/tenant_id/role) from the resolved user and attach it to
   `request.state.token_data`.
3. If neither succeeds, leave `request.state.token_data = None` (anonymous — public routes
   still work).
4. The middleware **never raises 401 by itself** for missing/invalid credentials on a
   route that may be public. Enforcement of "this route requires auth" stays with
   `get_current_user` / an equivalent dependency (consistent with the existing IOC docs
   note: "`get_ioc` is not an authentication gate"). A malformed credential is treated as
   anonymous, exactly like the current `get_ioc` behavior.

The middleware uses request-scoped resources (Redis, settings) it can obtain without the
IoC container (settings via `get_settings()`, Redis via the existing pool helper), because
middleware runs outside FastAPI's per-route dependency graph. **Decision needed** (open
question 1) on whether API-key lookup should run in middleware directly or be deferred to
first access in the mapper.

### 2. `get_ioc` reads identity from `request.state` instead of re-decoding

`app/infrastructure/ioc.py`:

- Change `get_ioc` to accept the `Request` and read `request.state.token_data` (set by the
  middleware) rather than decoding the bearer token itself. This makes the middleware the
  single place identity is established (requirement #2 and #6), and removes the duplicate
  decode currently in `get_ioc`.
- The container's `claims` / `tenant_id` properties are unchanged in shape.
- Backward-compat: if `request.state.token_data` is unset (e.g. middleware not yet run in a
  test harness), fall back to `None` (anonymous). No silent re-decode.

### 3. `CurrentUserMapper` — confirm it is the single read surface (small additions)

`app/mappers/current_user_mapper.py`:

- Keep reading identity from `self._ioc.claims`. No structural change to existing properties.
- Add identity accessor parity with the PHP mapper where it makes sense and is backed by
  available data: a `get_id()` / `get_role()` style is **not** added (Python uses
  properties: `user_id`, `role`); the PHP method names are intentionally mapped to the
  existing Pythonic properties. This is a naming-convention decision (open question 3).
- Add the **API-key lazy-load extension point** described in the existing docstring only
  if open question 1 resolves to "mapper lazy-loads the user/profile". Otherwise leave the
  documented extension point as-is.

### 4. API-key support primitives (interface + stub only; no `users`/`api_keys` table)

Because there is no `users` or `api_keys` table yet (same constraint that left
`NotImplementedUserLookupService` a stub), API-key support lands as **interface + stub**,
matching the established pattern:

- `app/storages/api_key_storage.py` — `ApiKeyStorage(AbstractStorage)` with
  `async def get_user_by_api_key(self, api_key: str) -> AuthUser | None`. Until the
  `api_keys` table exists, it returns `None` (or raises a clear `NotImplementedError` —
  open question 2) so the middleware's API-key branch is wired but inert.
- `app/infrastructure/settings.py` — add the API-key header name as a setting
  (`api_key_header: str = "X-API-Key"`), so the header is not hardcoded.

This keeps the API-key path fully wired (requirement #3) without inventing schema that the
database agent must own.

### 5. Wiring — `app/main.py`

- Register the new auth middleware on `app` (added before the router include so it runs for
  all routes).

### 6. Documentation (requirement #7)

- `docs/architecture/IOC.md` — update the "Carried State" / "Security Properties" sections
  to state that `claims` is now established by the **auth middleware** and read by
  `get_ioc` from `request.state`, not decoded in `get_ioc`. Update the note about
  `get_ioc` not being an auth gate to reference the middleware.
- `.claude/rules/RULES.md` — update the **Authentication** subsection: "Token verification
  happens in middleware" is already stated; add the API-key second strategy and the
  `CurrentUserMapper` single-read-surface rule, and that controllers only read identity via
  `self.CurrentUserMapper`.
- `CLAUDE.md` — confirm the Infrastructure/auth description still matches; adjust only if a
  statement becomes inaccurate.
- `docs/application-stack/auth.md` (if present) — add the middleware + API-key flow.
- This plan's status → `implemented` (docs-writer, at the end).

## Out of scope

- The `users` table, `api_keys` table, Alembic migrations, and seed SQL — these are
  database-agent work and are deliberately deferred (the lookup stays a stub, identical to
  the existing `NotImplementedUserLookupService` precedent).
- A real session/cookie path. The PHP "Web session" path maps to the **JWT bearer** path
  here (requirement #4 says the UI uses the JWT refresh-token flow), so no separate
  server-side web-session mechanism is built.
- API-key issuance/rotation endpoints, hashing scheme for stored API keys, and rate
  limiting — follow-ups once the schema exists.
- Changing the login/refresh/logout endpoints or refresh-token storage.
- Any frontend / UI work.
- Role-based authorization helpers (`require_role`) beyond the existing `is_admin()` /
  `is_manager()`.

## Acceptance criteria

- A request with a valid `Authorization: Bearer <jwt>` results in
  `request.state.token_data` being set by the middleware, `ioc.claims` returning that
  `TokenData`, and `CurrentUserMapper.is_initialized()` returning `True` with correct
  `user_id` / `tenant_id` / `role`.
- A request with no credentials results in `ioc.claims is None` and
  `CurrentUserMapper.is_initialized()` returning `False`; public routes still succeed.
- A request with a malformed/expired JWT is treated as anonymous by the middleware (no
  500), and protected routes still return 401 via `get_current_user`.
- The API-key branch is wired: a request carrying the configured API-key header invokes
  `ApiKeyStorage.get_user_by_api_key`; with the current stub it resolves to anonymous (or a
  clear not-implemented signal per open question 2) — no crash, no partial identity.
- `get_ioc` no longer decodes the JWT itself; identity comes solely from
  `request.state.token_data` set by the middleware (verified by reading the source: the
  `decode_access_token` call is gone from `get_ioc`).
- Controllers contain no auth/identity-resolution logic; they only read
  `self.CurrentUserMapper`. `BaseController` is unchanged in responsibility.
- `tenant_id` / `role` are still sourced only from verified JWT claims or the API-key
  lookup result — never from request body/query.
- `python -c "import app.main"` imports cleanly with the middleware registered.
- Docs in `docs/architecture/IOC.md` and `.claude/rules/RULES.md` accurately describe the
  middleware-driven initialization and the two strategies.

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `app/infrastructure/auth_middleware.py` | created (JWT + API-key strategies) | implementer |
| `app/infrastructure/ioc.py` | updated (`get_ioc` reads `request.state.token_data`; drop in-dependency decode) | implementer |
| `app/storages/api_key_storage.py` | created (interface + inert stub) | implementer |
| `app/infrastructure/settings.py` | updated (`api_key_header` setting) | implementer |
| `app/mappers/current_user_mapper.py` | updated only if open Q1/Q3 require it | implementer |
| `app/main.py` | updated (register middleware) | implementer |
| `docs/architecture/IOC.md` | updated | docs-writer |
| `.claude/rules/RULES.md` | updated (Authentication section) | docs-writer |
| `CLAUDE.md` | updated only if a statement becomes inaccurate | docs-writer |
| `docs/application-stack/auth.md` | updated if present | docs-writer |
| `docs/plans/2026-05-20-auth-middleware-current-user.md` | status → implemented at end | docs-writer |

## Risks

- **Middleware vs dependency ordering**: `BaseHTTPMiddleware` runs outside the per-route
  dependency graph and cannot use `Depends`. It must obtain settings/Redis via the existing
  module-level helpers, and must attach to `request.state`. Risk: subtle differences in how
  `request.state` is read back inside `get_ioc`. Mitigated by reading `request.state` with a
  safe default.
- **Double source of truth during transition**: if the in-`get_ioc` decode is removed but a
  test harness bypasses the middleware, identity will be `None`. Mitigated by the documented
  fallback and by updating any affected tests.
- **API-key path is inert**: with no `api_keys` table, the API-key branch cannot be
  end-to-end tested. This is intentional and mirrors the existing auth stub precedent;
  called out so reviewers do not treat it as incomplete.
- **Security surface**: this touches auth, trust boundaries, and credential parsing →
  **security agent is required** after review. Focus: API-key header parsing, ensuring
  malformed credentials never partially initialize identity, no credential logging, no
  identity from body/query, alg pinning preserved.
- **Header naming / precedence**: if both a bearer JWT and an API key are present, define
  precedence (proposed: JWT wins). Open question 4.
- **No live Redis/DB in CI**: verification limited to imports + unit-level behavior unless
  the Docker stack is started.

## Agent decisions

- planner: this plan (no code written).
- ui-designer: not required (no UI scope).
- database: **not required now** — no schema/migration in this task; `users` / `api_keys`
  tables are deferred and will go through the database agent when implemented.
- implementer: owns all `app/` files in the table above, to this contract.
- reviewer: verify middleware runs before controllers, `get_ioc` no longer decodes,
  controllers carry no auth logic, layer boundaries, type hints, no `print`, anonymous
  fallback correctness.
- security: **required** (auth, trust boundary, credentials). Run after reviewer.
- docs-writer: owns all doc/MD updates and sets this plan to `implemented`.
- spec-writer: optional — the change is infrastructural (no new user-facing endpoint).
  Recommend **skip** unless the user wants a plain-language note about API-key access.
- version-control: commit plan + code + docs together at the end.

## Open questions for approval

1. **API-key resolution location**: resolve the API key to a user **in the middleware**
   (eager, attaches full `TokenData` like the JWT path) — recommended for symmetry — or
   **lazy** in `CurrentUserMapper` on first access (closer to the PHP "lazy-load API key
   from Storage")? Recommendation: **eager in middleware**, so both strategies converge on
   the same `request.state.token_data` and `CurrentUserMapper` stays a pure reader.
2. **Stub behavior for `ApiKeyStorage`**: return `None` (treat as anonymous, no crash) or
   raise `NotImplementedError` (loud, like `NotImplementedUserLookupService`)?
   Recommendation: **return `None`** so the API-key branch is non-fatal until the table
   exists, while keeping the wiring present.
3. **Method naming on `CurrentUserMapper`**: keep the existing Pythonic properties
   (`user_id`, `role`, `is_admin()`, `is_manager()`) rather than mirroring the PHP method
   names (`getId()`, `isWaiter()`)? Recommendation: **keep Pythonic** — RULES mandates
   `snake_case` methods/properties and the warehouse domain has no "waiter" role.
4. **Credential precedence** when both bearer JWT and API key are present.
   Recommendation: **JWT wins**, API key is only tried when no valid JWT is present.
5. **`CurrentUserMapper` profile lazy-load**: implement the documented `get_profile()`
   extension point now (needs `UserStorage`, which doesn't exist) or leave it as a
   documented extension point? Recommendation: **leave as extension point** (out of scope
   until `UserStorage` lands).

## Approval log

- 2026-05-20: plan drafted, awaiting user approval. Open questions above must be resolved
  (or accepted as recommended) before implementation starts.
- 2026-05-20: plan approved. Resolutions: (1) API-key resolution eager in middleware;
  (2) presented-but-unresolvable API key → 401 immediately (no header → anonymous);
  (3) keep Pythonic mapper accessors; (4) JWT precedence over API key; (5) leave
  `get_profile()` lazy-load as a documented extension point. Implemented end to end:
  `AuthMiddleware` (JWT + API-key strategies) created; `get_ioc` now reads
  `request.state.token_data` (no in-dependency decode); `ApiKeyStorage` inert stub added;
  `api_key_header` setting added; middleware registered in `app/main.py`; docs updated
  (`IOC.md`, `RULES.md`, `application-stack/auth.md`). `CurrentUserMapper` unchanged
  (Pythonic accessors kept). Verified via TestClient: valid JWT → identity; no creds →
  anonymous; malformed JWT → anonymous; presented API key → 401; JWT+API key → JWT wins.
- 2026-05-20: post-implementation adjustments per user feedback (referencing
  `docs/architecture/ActiveUserMapper.php`):
  - **`CurrentUserMapper` now holds the full user record**, not just JWT claims —
    the Python equivalent of `ActiveUserMapper` holding `$userData`. Claim-backed
    identity (`user_id`/`tenant_id`/`role`, `is_admin()`/`is_manager()`) stays a
    cheap no-DB read; the full `AuthUser` is lazy-loaded and memoized via
    `await load()` (then read through `user` / `email`), and `get_api_key()`
    lazy-loads the user's API key — mirroring the PHP lazy-load. The async DB load
    cannot live in a property (`await`), so loading is `await load()` and profile
    properties read the memoized record. New `UserStorage` added as the load
    source. The auth *mechanism* (JWT vs API key) remains abstracted away — the
    mapper only ever sees a verified user. **Middleware JWT/API-key strategy
    unchanged**, per the user's instruction.
  - **`ApiKeyStorage` (and new `UserStorage`) stubs now raise `404 Not Found`**
    instead of returning `None`, making it explicit that the feature is not yet
    implemented (the `api_keys` / `users` tables do not exist), distinct from a
    genuine "not found" (a `401` once a real API-key lookup exists). The
    middleware catches the `HTTPException` from the API-key stub and surfaces the
    404 — required because an exception raised inside `BaseHTTPMiddleware` would
    otherwise become a 500.
  Verified via TestClient: presented API key → 404 (not-implemented);
  `CurrentUserMapper.load()` → 404 from `UserStorage` stub; valid JWT → identity
  with no DB hit; anonymous and malformed-JWT paths unchanged; JWT+API key → JWT
  wins. App still imports cleanly.
