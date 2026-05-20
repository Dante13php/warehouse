# Mapper Layer + Request/Validation Pattern Standardization

## Status

`implemented`

## Source task or spec

Port two additional CloudSale (PHP) architectural patterns into Warehouse
(Python 3.12+ / FastAPI / SQLAlchemy async), per the orchestrator task brief:

1. **Mapper layer** — a new architectural layer holding per-request contextual
   state (the currently authenticated user) with lazy-loading and role-check
   helpers. CloudSale's `AbstractMapper` + `ActiveUserMapper` become Warehouse's
   `AbstractMapper` + `ActiveUserMapper`.

2. **Request pattern standardization** — Pydantic already replaces the
   ~1100-line PHP `RequestValidator` DSL engine. Only the two pieces with **no**
   Pydantic equivalent are ported:
   - the `expandable:` query grammar → a small FastAPI dependency parsing
     `?expand=resource[field1,field2]`.
   - the unified validation-error envelope (`{"error": {"code": "V001", ...}}`)
     → a custom 422 exception handler.

The validation *engine* itself is explicitly NOT ported.

### Current state (commit a32c166 / present worktree)

- `app/infrastructure/ioc.py` resolves four suffixes only: `*Service`,
  `*Storage` (instantiated, memoized), `*Request`, `*Error` (factories). No
  `*Mapper` suffix.
- `Ioc.__init__` carries `session`, `tenant_id`, `redis`, `settings`. `tenant_id`
  is the only JWT-derived value; `get_ioc` decodes the token and extracts only
  `tenant_id` (line 295), discarding `sub` and `role`.
- `get_ioc` swallows `JWTError` and sets `tenant_id=None` for invalid tokens on
  public routes (lines 297-301). Auth enforcement is separate
  (`app/helpers/security.py` `get_current_user`).
- `BaseController` / `AbstractService` / `AbstractStorage` all use the same
  `__init__(self, ioc)` + `__getattr__` delegation to the container.
- `app/main.py` registers no exception handlers and only includes the auth
  router.
- `TokenData` (`app/data/token.py`) is a dataclass carrying `sub`, `tenant_id`,
  `role` with a `from_claims` factory.
- No `app/mappers/` package exists.

### CloudSale source design (do not re-design)

`AbstractMapper`: container-proxying base (like `AbstractService`).
`ActiveUserMapper`: holds the verified user row (`init($userData)`), exposes
`getId()`, `getUsername()`, `isEnabled()`, role checks (`isWaiter`/`isManager`),
and lazy-loads `getApiKey()` from `ApiKeyStorage` cached on the instance.
IoC resolves `*Mapper` from a **flat** `mappers/` namespace.

## Confirmed user decisions (do not re-ask)

1. **A Mapper is a per-request context holder** — not a DTO, not a service. It
   holds mutable state set once per request, provides computed properties and
   role-check methods, and may lazy-load related data from Storage (cached on the
   instance).
2. **`*Mapper` is resolved by IoC**, flat namespace (`app/mappers/`, like
   `app/storages/`), instantiated and memoized per request (same lifetime class
   as `*Service`/`*Storage`).
3. **`ActiveUserMapper` is the Warehouse equivalent of CloudSale's `ActiveUserMapper`.** It
   holds the verified JWT claims (`user_id`/`sub`, `tenant_id`, `role`) and
   exposes those plus role checks. It reads claims from the container rather than
   requiring an explicit post-construction `init()` call; the container is the
   carrier of the verified claims.
4. **Validation engine is NOT ported.** Only the `expand` grammar (small FastAPI
   dependency) and the unified 422 envelope (custom handler) are built.
5. **Dependency order:** IoC `*Mapper` wiring lands before the concrete
   `ActiveUserMapper`.

## Scope

### Part A — Mapper layer

#### A1. IoC `*Mapper` suffix wiring — `app/infrastructure/ioc.py`

- Add `"Mapper": "app.mappers"` to `_SUFFIX_TO_PACKAGE`.
- Add `"Mapper"` to `_INSTANTIATED_SUFFIXES` (mappers are request-scoped,
  memoized instances constructed with `(self)` — same path as `*Service`).
- No change to `_load_class` / `_find_class_in_package` (the recursive scan
  already works for a flat `app/mappers/` package; a flat package is just a tree
  of depth 1).
- Update the module docstring suffix table (lines 16-24) to add the `*Mapper`
  row.

Because `*Mapper` joins `_INSTANTIATED_SUFFIXES`, `__getattr__` →
`_resolve_instance` → `target(self)` already handles construction and
memoization with no further branching. No new factory class needed.

#### A2. `app/mappers/__init__.py`

- New empty package marker (so `pkgutil.walk_packages` and `importlib` can scan
  `app.mappers`).

#### A3. `app/mappers/abstract_mapper.py` — `AbstractMapper`

Container-proxying base, identical shape to `AbstractService` /
`AbstractStorage` (RULES: "all layers explicit"; do not share a base across
layers):

```python
from __future__ import annotations
from typing import Any
from app.infrastructure.ioc import Ioc

class AbstractMapper:
    def __init__(self, ioc: Ioc) -> None:
        self._ioc = ioc

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
```

The `_`-guard prevents `__getattr__` recursion before `_ioc` is set and stops
dunder lookups from triggering IoC resolution (same guard the other base classes
use).

#### A4. `app/mappers/active_user_mapper.py` — `ActiveUserMapper`

The Warehouse `ActiveUserMapper`. Holds verified identity sourced from the
container's JWT-derived state and exposes typed properties + role checks. Reads
claims from the container (decision 3) — no explicit `init()` step required at
call time.

Design constraints:

- Properties `user_id`, `tenant_id`, `role` read the verified claims. The
  container today exposes only `tenant_id`; `sub`/`role` are decoded in `get_ioc`
  and discarded. This plan extends the container to carry the full verified
  claims (see A5) so the mapper has a single source of truth.
- Accessing identity on an unauthenticated request raises a clear error
  (mirroring CloudSale's `ActiveUserMapper` throwing when uninitialized). Use
  `IocResolutionError` is wrong here — define/raise a dedicated error (see A6).
- Role checks: `is_admin()`, `is_manager()` (+ any further roles) compare
  `self.role` against the Warehouse role values. NOTE: the Warehouse role
  vocabulary is not yet codified in a constant; this plan introduces the role
  checks against string literals matching the JWT `role` claim and flags role
  enumeration as a follow-up (see Risks R5). The mapper does **not** invent a
  role system — it checks the claim value already carried in the token.
- `is_initialized()` → returns whether verified claims are present on the
  request (i.e. an authenticated request), the analogue of CloudSale's
  `isInitialized()`.
- Optional lazy profile load (`get_profile()` / future) is documented as the
  extension point but only built if a `UserStorage` exists. Since no SQL
  `UserStorage` exists yet (auth uses `NotImplementedUserLookupService`), the
  lazy-load method is **stubbed/omitted** in this change and listed as out of
  scope; the mapper structure leaves room for it (cache attribute + method shape
  documented in a comment). This keeps the change to identity claims only.

Sketch:

```python
class ActiveUserMapper(AbstractMapper):
    @property
    def user_id(self) -> str: ...      # from verified sub claim, else raise
    @property
    def tenant_id(self) -> str: ...    # verified tenant_id, else raise
    @property
    def role(self) -> str: ...         # verified role, else raise
    def is_initialized(self) -> bool: ...   # claims present?
    def is_admin(self) -> bool: ...
    def is_manager(self) -> bool: ...
```

#### A5. Container carries full verified claims — `app/infrastructure/ioc.py` + `get_ioc`

To give `ActiveUserMapper` a single source of truth without a post-construction
`init()`:

- Extend `Ioc.__init__` to accept the verified `TokenData | None` (the decoded
  claims) in addition to / in place of the standalone `tenant_id`. Keep the
  existing `tenant_id` property working (derive it from the claims when present)
  so no existing call site breaks.
- `get_ioc` already calls `decode_access_token` → `TokenData`; pass that
  `TokenData` (or `None`) into the `Ioc` constructor instead of pulling only
  `claims.tenant_id`.
- Expose a private accessor on the container (e.g. `_claims` /
  `ioc.current_claims`) that `ActiveUserMapper` reads. Naming must avoid
  colliding with `__getattr__` suffix resolution — use a leading-underscore
  backing field plus a non-suffix property name (e.g. `claims`), or have the
  mapper read `self._ioc`-style state via an explicit method. Implementer to
  pick the cleanest non-colliding name; `tenant_id` precedent (a plain property
  on `Ioc`) is the model.

This is the minimal, backward-compatible extension. The existing `tenant_id`
contract (claims-only, no setter, never from body/query) is preserved.

#### A6. `app/errors/auth/unauthenticated_error.py` — `UnauthenticatedError`

A bare exception (matching the current auth error style — `InvalidTokenError`
etc. are bare `Exception` subclasses) raised by `ActiveUserMapper` identity
properties when no verified claims are present. Resolves via the existing
`*Error` IoC suffix (`ioc.UnauthenticatedError.target` for catching). Kept
consistent with the current pre-coded-error-model state of the repo (the full
`ApplicationError` model is a separate, not-yet-built pattern #9).

### Part B — Expand query-param parser

#### B1. `app/helpers/expand.py` — expand grammar parser + FastAPI dependency

Parse `?expand=resource[field1,field2],other` into a typed structure. Pure
function + a thin FastAPI dependency wrapper:

```python
@dataclass
class ExpandSpec:
    resource: str
    fields: tuple[str, ...]

def parse_expand(raw: str | None) -> dict[str, ExpandSpec]: ...

def expand_param(expand: str | None = Query(default=None)) -> dict[str, ExpandSpec]:
    return parse_expand(expand)
```

- Grammar: comma-separated entries; each entry is `name` or `name[f1,f2,...]`.
- Malformed input raises a validation error that flows through the **unified 422
  envelope** (Part C) — i.e. raise `RequestValidationError` or a dedicated
  validation error the Part C handler formats. Implementer chooses the mechanism
  that routes through the same envelope (decision: reuse FastAPI's
  `RequestValidationError` so one handler covers both Pydantic and expand
  errors).
- Pure parser is unit-testable without FastAPI.
- This is a **helper**, not a container-resolved layer (helpers are plain
  importable modules per existing convention — `app/helpers/jwt.py`, etc.). No
  `*Helper` IoC suffix is introduced.

### Part C — Unified validation-error envelope

#### C1. `app/main.py` — custom 422 handler

Register a `RequestValidationError` exception handler that reshapes FastAPI's
default 422 body into the CloudSale envelope:

```python
{"error": {"code": "V001", "message": "...", "details": {...}}}
```

- `code` = `"V001"` (the CloudSale validation code).
- `message` = a stable human message ("The request contains invalid query or
  body parameters.").
- `details` = the per-field errors from `exc.errors()` (location + message),
  reshaped to a clean dict/list (strip the noisy internal `ctx`/`url` fields).
- Status code stays **422**.
- Handler lives where handlers are registered (`app/main.py`); the envelope
  builder may be a small function in `app/helpers/` or inline. Keep it one place
  so the future `ApplicationError` handler (pattern #9, #12) can sit beside it.

This is the only validation-envelope piece; no `ApplicationError` /
`ErrorDefinitions` map is built here (that is the separate pattern #9, still "To
build").

### Part D — Documentation

- `docs/architecture/CLOUDSALE_PATTERNS.md`: add a new **Mapper layer** pattern
  section (CloudSale `AbstractMapper`/`ActiveUserMapper` → Warehouse
  `AbstractMapper`/`ActiveUserMapper`, status **Built**); update the Status
  summary table (add the row); update section 1's note that lists "No `*Mapper`
  ... suffix is wired" to reflect that `*Mapper` is now wired; in section 8 mark
  the expand grammar + unified envelope as built.
- `docs/architecture/IOC.md`: add `*Mapper` to the Resolution Rules table and the
  Path Convention table; note flat nesting and instance/memoized lifetime; add a
  `ActiveUserMapper`/`AbstractMapper` row to the path table; document the
  container now carrying verified claims.
- `.claude/rules/RULES.md`: add Mapper to the Layers/Layer-Rules sections
  (Controller → Request → Service → **Mapper** (context) → Storage → Data),
  describe what a Mapper is and is not, and add `mappers/` to the Folder
  Structure block.
- This plan file → `implemented` with a "What was built" section at the end.

## Out of scope

- The ~1100-line PHP `RequestValidator` validation DSL engine — Pydantic
  replaces it. No rule-string parser, no `AbstractRequest` `RULES` constant.
- The full coded-error model (`ApplicationError`, `ErrorDefinitions`, central
  `ApplicationError` handler, `ErrorFactory.throw`) — that is pattern #9, a
  separate task. Only the `V001` validation 422 envelope is built here.
- A SQL `UserStorage` and the mapper's lazy full-profile load — no SQL user
  store exists yet (auth uses `NotImplementedUserLookupService`). The mapper
  exposes identity claims only; the lazy-profile extension point is documented,
  not implemented.
- A formal Warehouse role enumeration/constant — the mapper checks the `role`
  claim value directly; codifying the role vocabulary is a follow-up.
- `*Helper` IoC suffix — helpers stay plain importable modules.
- The `{ "data": ... }` success envelope (pattern #12) and page models — not in
  this task.
- Frontend / UI — none.
- Database schema, migrations, seed SQL — none required (no table changes).

## Acceptance criteria

1. `ioc.py` resolves `*Mapper`: `"Mapper": "app.mappers"` in
   `_SUFFIX_TO_PACKAGE` and `"Mapper"` in `_INSTANTIATED_SUFFIXES`; docstring
   suffix table updated.
2. `app/mappers/__init__.py`, `app/mappers/abstract_mapper.py`
   (`AbstractMapper`) and `app/mappers/active_user_mapper.py`
   (`ActiveUserMapper`) exist; `AbstractMapper` has the `__init__(self, ioc)` +
   guarded `__getattr__`.
3. `ioc.ActiveUserMapper` resolves to a memoized per-request instance
   (`ioc.ActiveUserMapper is ioc.ActiveUserMapper` within one request).
4. `ActiveUserMapper` exposes `user_id`, `tenant_id`, `role` (from verified
   claims), `is_initialized()`, `is_admin()`, `is_manager()`. Identity
   properties raise `UnauthenticatedError` (resolvable via
   `ioc.UnauthenticatedError.target`) when no verified claims are present.
5. The container carries the full verified claims (`TokenData | None`) sourced
   only from `get_ioc`'s `decode_access_token`; the existing `tenant_id` property
   still returns the same value for authenticated and public requests, and there
   is still no setter and no body/query source.
6. `app/helpers/expand.py` exposes a pure `parse_expand(raw)` and a FastAPI
   `expand_param` dependency; `?expand=recipe[products,name],supplier` parses to
   the expected structure; malformed input produces a 422 routed through the
   unified envelope.
7. `app/main.py` registers a `RequestValidationError` handler returning HTTP 422
   with body `{"error": {"code": "V001", "message": ..., "details": ...}}`; an
   invalid login body now returns that envelope instead of the raw FastAPI 422.
8. `python -c "import app.main"` imports cleanly.
9. Existing auth flows still pass: invalid login body → 422 (now enveloped),
   `/auth/refresh` unknown token → 401, `/auth/logout` → 204.
10. All new/changed code: full type hints, `logging` not `print`, no mutable
    default arguments, layer boundaries respected, files `snake_case`, classes
    `PascalCase`.
11. Docs updated: `CLOUDSALE_PATTERNS.md` (Mapper section + status table + section
    1/8 notes), `IOC.md` (`*Mapper` rows + claims note), `RULES.md` (Mapper layer
    + folder structure).

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `app/infrastructure/ioc.py` | updated (`*Mapper` suffix, instantiated set, carry `TokenData` claims, docstring) | implementer |
| `app/mappers/__init__.py` | created (package marker) | implementer |
| `app/mappers/abstract_mapper.py` | created (`AbstractMapper`) | implementer |
| `app/mappers/active_user_mapper.py` | created (`ActiveUserMapper`) | implementer |
| `app/errors/auth/unauthenticated_error.py` | created (`UnauthenticatedError`) | implementer |
| `app/helpers/expand.py` | created (expand parser + dependency) | implementer |
| `app/main.py` | updated (422 `RequestValidationError` handler) | implementer |
| `docs/architecture/CLOUDSALE_PATTERNS.md` | updated (Mapper section, status table, §1/§8) | docs-writer |
| `docs/architecture/IOC.md` | updated (`*Mapper`, claims) | docs-writer |
| `.claude/rules/RULES.md` | updated (Mapper layer, folder structure) | docs-writer |
| `docs/plans/2026-05-20-mapper-layer-and-request-patterns.md` | this plan → implemented at end | docs-writer |

## Risks

- **R1 — `__getattr__` recursion / dunder masking in `AbstractMapper`.** Same
  failure mode as the other base classes. Mitigation: identical
  `if name.startswith("_"): raise AttributeError(name)` guard. Reviewer verifies.
- **R2 — Container claims extension breaks existing `tenant_id` consumers.**
  Storages and `get_ioc` depend on `ioc.tenant_id`. Mitigation: keep the
  `tenant_id` property and its exact return contract; derive it from the carried
  `TokenData` when present, else `None`. Acceptance criterion 5 + auth flow tests
  (criterion 9) cover this.
- **R3 — Name collision between the claims accessor and IoC suffix resolution.**
  A property/attribute on `Ioc` named to end in a known suffix would shadow
  resolution. Mitigation: the claims accessor must NOT end in
  `Service/Storage/Request/Error/Mapper` (e.g. use `claims` or
  `current_claims`). Reviewer verifies the chosen name.
- **R4 — Mapper accessed on a public/anonymous request.** `ActiveUserMapper`
  identity properties must fail loudly, not return `None` (CloudSale throws).
  Mitigation: raise `UnauthenticatedError`; `is_initialized()` lets callers check
  first. Document that public routes must not read identity without guarding.
- **R5 — Role vocabulary not codified.** `is_admin()`/`is_manager()` compare
  against role-claim string literals that are not yet centralized in a constant.
  Risk of drift between token issuance and mapper checks. Mitigation: implementer
  uses the same literal(s) the JWT `role` claim is issued with; a follow-up to
  introduce a `Role` enum is flagged (not in scope). Reviewer confirms literals
  match `create_access_token`'s `role` source.
- **R6 — Expand parser as a user-input surface.** `?expand=` is user-controlled.
  The parser must only produce inert `ExpandSpec` strings; it must NOT feed
  resource/field names into `getattr(ioc, ...)` or SQL identifiers without
  whitelisting. Mitigation: parser returns plain strings; consumers (future
  storages) are responsible for whitelisting fields against the Data field set.
  Document this contract in the helper. Security review recommended (see Agent
  decisions).
- **R7 — Envelope handler swallowing non-validation 422s.** Only
  `RequestValidationError` is reshaped; `ResponseValidationError` and other
  exceptions are untouched. Mitigation: register the handler specifically on
  `RequestValidationError`, not on generic `Exception`/`HTTPException`.

## Agent decisions

- **planner:** this plan, no code. Brainstorming bypassed — the orchestrator
  brief fully specifies the target design (concrete CloudSale source, explicit
  in/out of scope, dependency order, confirmed mapper semantics). No open design
  questions remain that block planning; the two flagged follow-ups (role enum,
  lazy profile load) are explicitly out of scope.
- **ui-designer:** not required (no UI scope).
- **database:** not required (no schema/migration/seed change — mapper reads JWT
  claims; no new tables; no SQL `UserStorage` introduced).
- **implementer:** owns all code files in the impacted-files table. Build order:
  (1) IoC `*Mapper` wiring + claims carry (A1, A5), (2) `AbstractMapper` +
  package + `UnauthenticatedError` (A2, A3, A6), (3) `ActiveUserMapper` (A4),
  (4) expand helper (B1), (5) 422 handler (C1). IoC changes precede concrete
  mappers (dependency order, decision 5).
- **reviewer:** verify `__getattr__` guard in `AbstractMapper`; `*Mapper`
  wired into both `_SUFFIX_TO_PACKAGE` and `_INSTANTIATED_SUFFIXES`; memoization
  works; `tenant_id` contract unchanged; claims accessor name does not collide
  with a suffix (R3); identity properties raise on anonymous requests (R4); role
  literals match token issuance (R5); expand parser returns inert strings and
  routes errors through the 422 envelope (R6); handler scoped to
  `RequestValidationError` only (R7); type hints / logging / no mutable defaults
  / naming.
- **security:** **required** — review the expand parser as a user-input surface
  (R6: confirm no path from `?expand=` into dynamic attribute/SQL resolution
  without whitelisting) and confirm the container claims extension keeps
  `tenant_id`/identity sourced exclusively from verified JWT claims with no
  body/query path and no setter (R2/R3).
- **docs-writer:** update `CLOUDSALE_PATTERNS.md`, `IOC.md`, `RULES.md` per
  Part D; set this plan to `implemented` with a "What was built" section.
- **version-control:** commit plan + code + docs together in the final commit
  set at the end.

## What was built

All scope items delivered in build order per the plan:

**A1 — IoC `*Mapper` suffix wiring**: `"Mapper": "app.mappers"` added to `_SUFFIX_TO_PACKAGE`; `"Mapper"` added to `_INSTANTIATED_SUFFIXES`; docstring suffix table updated.

**A5 — Container carries full verified claims**: `Ioc.__init__` now accepts `token_data: TokenData | None` (replaces standalone `tenant_id` parameter). `ioc.claims` property exposes the full `TokenData`. `ioc.tenant_id` is now derived from `claims.tenant_id` — backward-compatible, no setter, no body/query source. `get_ioc` passes the full `TokenData` (or `None`) to the constructor.

**A2 — `app/mappers/__init__.py`**: empty package marker created.

**A3 — `app/mappers/abstract_mapper.py`**: `AbstractMapper` with `__init__(self, ioc)` + leading-underscore-guarded `__getattr__`.

**A6 — `app/errors/auth/unauthenticated_error.py`**: `UnauthenticatedError(Exception)` raised by `ActiveUserMapper` identity properties on unauthenticated requests.

**A4 — `app/mappers/active_user_mapper.py`**: `ActiveUserMapper(AbstractMapper)` exposing `user_id`, `tenant_id`, `role` (from `ioc.claims`), `is_initialized()`, `is_admin()` (`role == "admin"`), `is_manager()` (`role == "manager"`). Identity properties raise `UnauthenticatedError` when claims are absent. Role literals match `create_access_token` issuance.

**B1 — `app/helpers/expand.py`**: `parse_expand(raw)` pure parser + `expand_param` FastAPI dependency. Parses `?expand=resource[field1,field2],other`. Malformed input raises `RequestValidationError` with proper `msg` field routed through the unified 422 envelope.

**C1 — `app/main.py`**: `RequestValidationError` exception handler registered, returning HTTP 422 with `{"error": {"code": "V001", "message": ..., "details": [{"loc": [...], "msg": "..."}]}}`. Scoped to `RequestValidationError` only. `ctx`/`url` stripped.

**Documentation**: `docs/architecture/CLOUDSALE_PATTERNS.md`, `docs/architecture/IOC.md`, `.claude/rules/RULES.md` all updated per Part D.

## Approval log

- 2026-05-20: plan drafted (`draft`), awaiting user approval. Brainstorming
  bypassed — design fully specified by the orchestrator brief. Two items flagged
  as deliberate follow-ups (role enum, mapper lazy-profile load) and placed out
  of scope. Approve to proceed to implementer.
- 2026-05-20: user approved; implementation completed.
