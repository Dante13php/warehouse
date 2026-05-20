# Per-Request IoC Container

## Status

`implemented`

## Source task or spec

Implement a per-request IoC (Inversion of Control) container for the Warehouse
Python/FastAPI project and establish it as the **fundamental DI pattern** of the
product, replacing the current `Service Locator` anti-pattern entry and the manual
`_build_auth_service()` / `Depends(...)` wiring.

### Confirmed user decisions (do not re-ask)

1. **IoC replaces Service Locator** — `RULES.md` must remove `❌ Service Locator`
   from anti-patterns and add IoC as the official DI mechanism.
2. **Per-request scope** — a new `Ioc` instance is created per HTTP request and
   carries that request's `AsyncSession` and `tenant_id`. No app-level singleton.
3. **No manual dependency wiring** — no `Depends(get_xyz_service)` chains, no
   constructor parameter lists with injected services/storages. Everything is
   resolved dynamically by the container.

### Reference — CloudSale PHP pattern (ported to Python)

PHP resolves dependencies by class-name suffix via `__get` magic. The Python
equivalent is `__getattr__` + `importlib.import_module`. The PHP 1:1
namespace=path assumption does **not** apply — Python needs a snake_case path
conversion strategy because files are `snake_case.py` while classes are
`PascalCase`.

## Resolution design

The container exposes attributes named after the **class** to resolve. The
suffix of the requested name selects the layer, which selects the folder and the
nesting rule:

| Requested attribute | Suffix | Module path | Nesting |
|---|---|---|---|
| `ioc.AuthService` | `Service` | `app.services.<domain>.<module>` | nested by domain |
| `ioc.RefreshTokenStorage` | `Storage` | `app.storages.<module>` | flat |
| `ioc.LoginRequest` | `Request` | `app.requests.<domain>.<module>` | nested by domain |
| `ioc.InvalidCredentialsError` | `Error` | `app.errors.<domain>.<module>` | nested by domain |

### snake_case path conversion

`AuthService` → strip suffix `Service` → domain stem `Auth` → `auth`. PascalCase
to snake_case for both the domain segment and the module filename:

- `AuthService` → domain `auth`, module `app.services.auth.service`, class `AuthService`
- `RefreshTokenStorage` → flat, module `app.storages.refresh_token_storage`, class `RefreshTokenStorage`
- `LoginRequest` → domain `login`? No — request modules are per-action, so
  `LoginRequest` → `app.requests.<domain>.<module>`.

> **Open question (Q1, below):** the current code does not encode domain in
> nested module names the way PHP does (e.g. `service.py`, not `auth_service.py`;
> `login.py`, not `login_request.py`). The resolver therefore cannot derive the
> module file name purely from the class name for the nested layers. This plan
> proposes a **per-layer resolution strategy with an explicit, documented
> convention** rather than guessing. See Risks and Open Questions.

### Proposed resolver algorithm (per layer)

Because the existing nested files are named by *role* (`service.py`,
`user_lookup.py`) and per-*action* (`login.py`, `refresh.py`, `logout.py`),
not by `<Domain><Suffix>`, a pure class-name→path map is not derivable for every
class. The plan offers two candidate strategies and recommends one at approval:

- **Strategy A (registry-light, recommended):** the resolver maps by suffix to a
  layer, then scans that layer's package for a module exporting the requested
  class name. Resolution is by *class symbol*, not by file name. Cached per
  process. Works with the existing file names with zero renames.
- **Strategy B (convention-strict):** rename nested files to `<domain>/<thing>_<suffix>.py`
  (e.g. `services/auth/auth_service.py`, `requests/auth/login_request.py`) so the
  path is derivable from the class name exactly like PHP. Larger blast radius
  (renames + import updates) but a stricter, PHP-identical rule.

The plan defaults to **Strategy A** to honor "no manual wiring" without forcing
a rename of every file. Final choice is an approval gate (Q1).

## Scope

### New file — `app/infrastructure/ioc.py`

- `Ioc` class constructed per request with `session: AsyncSession`,
  `tenant_id: str | None`, `redis: Redis`, `settings: Settings`.
- `__getattr__(name)` resolves classes by suffix:
  - `*Service` → instantiate from `app.services` (nested), inject the `Ioc`
    itself so services pull their own collaborators (no constructor lists).
  - `*Storage` → instantiate from `app.storages` (flat).
  - `*Request` / `*Error` → return the **class** (these are constructed by
    FastAPI/raised directly, not container-instantiated) — or resolve as needed.
- Per-instance memoization: a resolved service/storage is cached on the `Ioc`
  instance so the same request reuses one instance (request scope).
- Service constructors change to accept a single `ioc: Ioc` and lazily pull
  collaborators (`self._ioc.RefreshTokenStorage`, `self._ioc.session`,
  `self._ioc.redis`, `self._ioc.settings`) — eliminating injected parameter lists.

### FastAPI integration

- A single dependency `get_ioc(...)` (in `ioc.py` or `helpers/security.py`)
  builds the per-request `Ioc` from the existing `get_db` / `get_redis` /
  `get_settings` dependencies and the verified identity (`tenant_id` from JWT
  claims when present; `None` for public endpoints like login).
- This is the **only** remaining `Depends`; it bootstraps the container, which
  is allowed per "per-request scope" (the container itself is request-scoped
  state, not a service-locator lookup of business services).

### Controller updates — `app/controllers/auth/router.py`

- Remove `_build_auth_service()` and the per-collaborator `Depends` imports.
- Each route takes `ioc: Ioc = Depends(get_ioc)` and calls
  `ioc.AuthService.login(...)` etc. Mutations still wrapped via
  `transaction_helper.wrap(ioc.session, ...)` (TransactionHelper resolved via the
  container or kept as a helper instance).

### Service updates — `app/services/auth/service.py`

- `AuthService.__init__(self, ioc: Ioc)`.
- Replace `self._user_lookup` / `self._refresh_storage` constructor params with
  lazy access through `self._ioc`.
- `db_name`, `redis`, `settings` read from `self._ioc` instead of method params
  where they are container-owned (keep method args that are true inputs like
  `email`, `password`, `refresh_token`).

## Out of scope

- Renaming existing files (unless Strategy B is approved at Q1).
- Any new business endpoints, warehouse/inventory/production/sales features.
- Database schema, migrations, seed SQL — none required.
- A general-purpose third-party DI framework (e.g. `dependency-injector`,
  `punq`) — the requirement is a bespoke per-request container.
- Frontend / UI work.
- Replacing `get_redis` / `get_db` / `get_settings` provider functions — they
  remain as the low-level resource providers the container consumes.

## Acceptance criteria

- `app/infrastructure/ioc.py` defines `Ioc` with `__getattr__`-based resolution
  using `importlib`, per the chosen strategy.
- Resolving `ioc.AuthService` returns a working `AuthService` with no manual
  collaborator wiring at the call site.
- `ioc.RefreshTokenStorage` resolves the flat storage; nested services/requests/
  errors resolve from their domain packages.
- An unknown name raises `AttributeError` (or a dedicated IoC error) with a clear
  message — never a silent `None`.
- Resolved services/storages are memoized for the lifetime of one `Ioc`
  (same instance returned twice within a request).
- `tenant_id` carried by the container is sourced only from verified JWT claims /
  request identity, never from request body or query — consistent with RULES
  multi-tenancy.
- `app/controllers/auth/router.py` contains no `_build_auth_service` and no
  per-collaborator `Depends`; routes use the container.
- `AuthService` no longer takes `user_lookup` / `refresh_storage` constructor
  params; it pulls them from the container.
- `python -c "import app.main"` imports cleanly; login/refresh/logout routes
  resolve their service via the container.
- `RULES.md`: `❌ Service Locator` removed from Anti-Patterns; IoC documented as
  the official DI mechanism with usage rules.
- `docs/architecture/IOC.md` exists and explains the pattern, resolution rules,
  request scope, and how to add a new dependency.
- All new code: full type hints, `logging` not `print`, no mutable defaults,
  layer boundaries respected.

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `app/infrastructure/ioc.py` | created (`Ioc` + `get_ioc`) | implementer |
| `app/controllers/auth/router.py` | updated (use container, drop manual wiring) | implementer |
| `app/services/auth/service.py` | updated (`__init__(ioc)`, lazy collaborators) | implementer |
| `app/services/auth/user_lookup.py` | reviewed; possibly resolved via container | implementer |
| `app/infrastructure/transaction.py` | reviewed; possibly exposed via container | implementer |
| `.claude/rules/RULES.md` | updated (remove Service Locator anti-pattern, add IoC) | docs-writer |
| `docs/architecture/IOC.md` | created (standalone architecture doc) | docs-writer |
| `docs/plans/2026-05-20-per-request-ioc-container.md` | this plan; status → implemented at end | docs-writer |

## Risks

- **R1 — Path derivation gap (primary):** existing nested files are named by role/
  action (`service.py`, `login.py`), not `<Domain><Suffix>.py`. A pure class→path
  rule (PHP-style) is not derivable. Mitigation: Strategy A (resolve by class
  symbol via package scan + cache) or Strategy B (rename to a strict convention).
  Decided at Q1.
- **R2 — Hidden coupling / "magic":** `__getattr__` resolution hides the
  dependency graph and defeats static analysis (IDE go-to-def, mypy on
  `ioc.AuthService`). Mitigation: document the convention thoroughly in
  `IOC.md`; keep suffix rules small and explicit; raise loud errors on miss.
- **R3 — RULES self-consistency:** RULES currently bans Service Locator and
  prescribes "constructor injection or dependency injection." Replacing it must
  not contradict the still-valid layer rules (controller no logic, storage-only
  DB). The IoC entry must clarify that controllers still don't hold logic and the
  container is request-scoped, not a global registry.
- **R4 — Request scope leakage:** the container holds an `AsyncSession`; it must
  not be shared across requests or cached at module level. Mitigation: build it
  only inside `get_ioc` per request; never memoize the `Ioc` itself globally.
- **R5 — `*Request`/`*Error` semantics:** request models are built by FastAPI
  from the body; errors are raised, not injected. The container should return the
  *class* for these (or not handle them at all). Clarify in `IOC.md` to avoid
  misuse. (Q2)
- **R6 — TransactionHelper ownership:** controllers wrap mutations. Decide
  whether TransactionHelper is resolved via the container (`ioc.transaction`) or
  remains a plain helper. (Q3)

## Agent decisions

- **planner:** this plan (no code). Brainstorming was bypassed because the three
  core decisions are pre-confirmed in the task; remaining ambiguities are raised
  as explicit Open Questions / approval gates rather than reopened design.
- **ui-designer:** not required (no UI scope).
- **database:** not required (no schema/migration).
- **implementer:** owns `ioc.py`, controller and service updates, to this contract.
- **reviewer:** verify resolution correctness, request-scope safety (no global
  `Ioc` caching, session not leaked), no manual wiring left, layer boundaries,
  type hints, loud errors on unknown names, tenant_id sourced from claims only.
- **security:** recommended — the container carries `tenant_id` and the session
  across the trust boundary. Confirm tenant_id is claims-only and that dynamic
  `importlib` resolution cannot be driven by user input (resolution names are
  literals in code, never from request data).
- **docs-writer:** update `RULES.md` (remove Service Locator, add IoC), create
  `docs/architecture/IOC.md`, set this plan to `implemented` with a "What was
  built" section.
- **version-control:** commit plan + code + docs together at the end.

## Open questions for approval

1. **Q1 — Resolution strategy:** Strategy A (resolve by class symbol via package
   scan, no renames — recommended) vs Strategy B (rename nested files to strict
   `<thing>_<suffix>.py` so paths are class-derivable, PHP-identical). Which?
2. **Q2 — `*Request` / `*Error` handling:** should the container resolve these at
   all (return the class), or restrict the container to `*Service` / `*Storage`
   only (the things that actually need wiring)? Recommended: container handles
   `*Service`/`*Storage` instances; documents `*Request`/`*Error` as out of its
   instantiation scope.
3. **Q3 — TransactionHelper:** resolve via container (`ioc.transaction`) or keep
   as a standalone helper imported in the controller? Recommended: expose via
   container for consistency, so controllers touch only `ioc`.
4. **Q4 — Security agent:** run the security agent after reviewer (recommended,
   because the container carries `tenant_id` + session across the boundary), or
   skip it for this infra-only change?

## What was built

Implemented per the resolved decisions: **Strategy B** (convention-strict, Q1),
PHP-style **factories** for `*Request`/`*Error` (Q2), **TransactionHelper via
container** (`ioc.transaction`, Q3), and the **security agent** was run (Q4).

### Resolved decisions applied

- **Q1 — Strategy B:** nested files renamed so the module file name is the
  snake_case of the class name; the resolver scans the layer package recursively
  so domain nesting need not be encoded in the class name.
- **Q2 — Factories:** `ioc.LoginRequest` returns a `GenericFactory`;
  `ioc.LoginRequest.get(...)` constructs. `ioc.InvalidCredentialsError` returns
  an `ErrorFactory`; `.get(...)` constructs, `.target` is the class.
- **Q3 — TransactionHelper:** exposed as `ioc.transaction` (memoized per request).
- **Q4 — Security:** security agent ran after reviewer; tenant_id is claims-only,
  importlib resolution cannot be driven by user input, session is request-scoped.

### Files created

- `app/infrastructure/ioc.py` — `Ioc`, `GenericFactory`, `ErrorFactory`,
  `IocResolutionError`, `get_ioc`.
- `app/errors/auth/invalid_credentials_error.py` — `InvalidCredentialsError`.
- `app/errors/auth/invalid_token_error.py` — `InvalidTokenError`.
- `app/errors/auth/expired_token_error.py` — `ExpiredTokenError`.
- `docs/architecture/IOC.md` — IoC architecture specification.

### Files renamed (Strategy B convention)

- `app/services/auth/service.py` → `app/services/auth/auth_service.py`.
- `app/services/auth/user_lookup.py` → `app/services/auth/not_implemented_user_lookup_service.py`
  (concrete class renamed `NotImplementedUserLookup` → `NotImplementedUserLookupService`).
- `app/requests/auth/login.py` → `app/requests/auth/login_request.py`.
- `app/requests/auth/refresh.py` → `app/requests/auth/refresh_request.py`.
- `app/requests/auth/logout.py` → `app/requests/auth/logout_request.py`.

### Files removed

- `app/errors/auth/errors.py` — split into one file per error class.

### Files updated

- `app/controllers/auth/router.py` — removed `_build_auth_service` and all
  per-collaborator `Depends`; routes take `ioc: Ioc = Depends(get_ioc)` and call
  `ioc.AuthService.<method>`; catch via `ioc.<Error>.target`.
- `app/services/auth/auth_service.py` — `__init__(self, ioc)`; collaborators and
  resources pulled lazily from the container; errors raised via `ioc.<Error>.get`.
- `app/storages/refresh_token_storage.py` — `__init__(self, ioc)`.
- `app/services/auth/not_implemented_user_lookup_service.py` — `__init__(self, ioc)`.
- `.claude/rules/RULES.md` — Service Locator anti-pattern replaced with a
  "Manual DI wiring" anti-pattern and a new **Dependency Injection** section;
  Controller layer rule updated to use `ioc` + `ioc.transaction`.

### Verification performed

- `python -c "import app.main"` imports cleanly.
- IoC unit checks: snake_case conversion; `*Service`/`*Storage` resolve and
  memoize (`is` identity); nested service resolves; `*Request`/`*Error` return
  factories whose `.get()` constructs and `.target` is the class; `ioc.transaction`
  memoized; unknown-suffix and missing-class both raise `IocResolutionError`;
  `ioc.session` raises when no session bound.
- Route wiring via FastAPI `TestClient`: `/auth/login` → 500 (NotImplemented user
  lookup, proving the container resolves the full chain), `/auth/refresh` → 401
  (error factory path), `/auth/logout` → 204, invalid email → 422.

## Approval log

- 2026-05-20: plan drafted (`draft`), awaiting user approval. Open questions
  Q1–Q4 must be resolved (or accepted as recommended) before implementation.
- 2026-05-20: Q1=Strategy B, Q2=factories, Q3=`ioc.transaction`, Q4=run security
  — all confirmed by user. Implemented, reviewed, security-reviewed, documented.
  Status set to `implemented`.
