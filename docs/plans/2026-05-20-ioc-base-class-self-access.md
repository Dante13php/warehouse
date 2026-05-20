# IoC Base-Class `self.X` Access Pattern

## Status

`implemented`

## What was built

- `app/controllers/base_controller.py` — `BaseController` with
  `__init__(self, ioc: Ioc = Depends(get_ioc))` and a leading-underscore-guarded
  `__getattr__` delegating to `self._ioc`.
- `app/services/abstract_service.py` — `AbstractService` with `__init__(self, ioc)`
  and the same guarded `__getattr__`.
- `app/storages/abstract_storage.py` — `AbstractStorage`, same shape, separate
  class for layer clarity.
- `app/controllers/auth/router.py` — added `AuthController(BaseController)` with
  `login` / `refresh` / `logout` methods using `self.AuthService` and catching
  `self.<Error>.target`; the three routes now inject
  `ctrl: AuthController = Depends(AuthController)` and delegate. No `ioc` parameter
  or `Depends(get_ioc)` remains in routes.
- `app/services/auth/auth_service.py` — now `AuthService(AbstractService)`;
  explicit `__init__` removed; every `self._ioc.X` replaced with `self.X`.
- `app/services/auth/not_implemented_user_lookup_service.py` — now extends
  `AbstractService`; explicit `__init__` removed.
- `app/storages/refresh_token_storage.py` — now `RefreshTokenStorage(AbstractStorage)`;
  the `redis` parameter dropped from `save` / `get_claims` /
  `get_and_delete_claims` / `delete`; methods read `self.redis`. `AuthService`
  call sites updated to stop passing `redis=`.
- Docs: `docs/architecture/IOC.md` (Base Classes section + Controller/Service/Storage
  usage and Instantiation Contract updated to the `self.X` pattern) and
  `.claude/rules/RULES.md` (Controller/Service/Storage layer rules).

### Verification performed

- `python -c "import app.main"` imports cleanly.
- Live route wiring via `TestClient` with a fake Redis: invalid login body → 422;
  `/auth/refresh` unknown token → 401 (error-factory self-access path);
  `/auth/logout` → 204; `/auth/login` valid body reaches
  `NotImplementedUserLookupService` (controller → service → storage self-access
  chain confirmed).
- Grep confirms zero `self._ioc.` / `ioc.` tokens in any controller, service, or
  storage business body (present only in the base classes and `ioc.py`); zero
  remaining `Depends(get_ioc)` outside `base_controller.py`.

## Original plan

## Source task or spec

Refactor the IoC integration so that controllers, services, and storages access
their collaborators and request-scoped resources through `self.X` — exactly like
PHP's `$this->AuthService` — instead of `ioc.X` / `self._ioc.X`. The `Ioc`
container must become invisible to business code: it lives only in the base
classes.

Current state (commit 489451c / present worktree):

- Routes declare `ioc: Ioc = Depends(get_ioc)` on every route function and call
  `ioc.AuthService.login(...)` directly. Controllers are plain functions.
- `AuthService.__init__(self, ioc)` stores `self._ioc` and every call site reads
  `self._ioc.settings`, `self._ioc.RefreshTokenStorage`, etc.
- `RefreshTokenStorage` / `NotImplementedUserLookupService` store `self._ioc` and
  receive `redis` as method parameters rather than reading `self.redis`.

Target state (user-specified, do not re-design):

- `BaseController.__init__(self, ioc: Ioc = Depends(get_ioc))` — `Depends` lives
  in the base class, not on each route. `__getattr__` delegates to `self._ioc`.
- Controllers become classes extending `BaseController`; call `self.AuthService`,
  catch via `self.InvalidCredentialsError.target`.
- Routes become thin: `ctrl: AuthController = Depends(AuthController)` then
  `return await ctrl.login(body)`.
- `AbstractService.__init__(self, ioc)` + `__getattr__` → services call
  `self.UserStorage`, `self.redis`, `self.settings`, `self.RefreshTokenStorage`.
- `AbstractStorage.__init__(self, ioc)` + `__getattr__` → storages call
  `self.session`, `self.tenant_id`, `self.redis`.

## Confirmed user decisions (do not re-ask)

1. Base classes own `Depends(get_ioc)` and `__getattr__`; business code never
   names `ioc` or `self._ioc`.
2. Routes inject the controller class itself via `Depends(AuthController)`;
   FastAPI resolves `BaseController.__init__`'s `ioc` parameter transitively.
3. `__getattr__` delegation is the access mechanism in all three base classes.

## Scope

### New file — `app/controllers/base_controller.py`

```python
from __future__ import annotations
from typing import Any
from fastapi import Depends
from app.infrastructure.ioc import Ioc, get_ioc

class BaseController:
    def __init__(self, ioc: Ioc = Depends(get_ioc)) -> None:
        self._ioc = ioc

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
```

- `_ioc` is set in `__init__`; the leading-underscore guard in `__getattr__`
  prevents infinite recursion before `_ioc` is assigned and prevents dunder
  lookups (`__deepcopy__`, etc.) from triggering IoC resolution.

### New file — `app/services/abstract_service.py`

```python
from __future__ import annotations
from typing import Any
from app.infrastructure.ioc import Ioc

class AbstractService:
    def __init__(self, ioc: Ioc) -> None:
        self._ioc = ioc

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
```

### New file — `app/storages/abstract_storage.py`

Same shape as `AbstractService` (separate class for layer clarity and to keep the
layer folders self-describing per RULES "all layers explicit").

### Updated — `app/controllers/auth/router.py`

- Add `AuthController(BaseController)` with async methods `login`, `refresh`,
  `logout` that contain the existing try/except → `HTTPException` mapping, calling
  `self.AuthService.<method>` and catching `self.<Error>.target`.
- Replace the three function routes' `ioc: Ioc = Depends(get_ioc)` with
  `ctrl: AuthController = Depends(AuthController)`; route body delegates to the
  controller method.
- Drop the `Ioc, get_ioc` import (no longer referenced in routes).

`AuthController` may live in `router.py` (alongside the routes, mirroring the
current single-file controller module) — no new domain file is required.

### Updated — `app/services/auth/auth_service.py`

- `class AuthService(AbstractService)` — remove the explicit `__init__`
  (inherited from `AbstractService`).
- Replace every `self._ioc.X` with `self.X`:
  `self.settings`, `self.redis`, `self.NotImplementedUserLookupService`,
  `self.RefreshTokenStorage`, `self.InvalidCredentialsError.get(...)`,
  `self.InvalidTokenError.get(...)`.

### Updated — `app/services/auth/not_implemented_user_lookup_service.py`

- `class NotImplementedUserLookupService(AbstractService)` — remove explicit
  `__init__`. No `self._ioc` usages in the body to change.

### Updated — `app/storages/refresh_token_storage.py`

- `class RefreshTokenStorage(AbstractStorage)` — remove explicit `__init__`.
- The current methods receive `redis: Redis` as a parameter. Per the task
  ("storages call `self.session`, `self.tenant_id`"), switch to reading
  `self.redis` inside the methods and drop the `redis` parameter from
  `save` / `get_claims` / `get_and_delete_claims` / `delete`.
- `AuthService` call sites updated accordingly (stop passing `redis=...`).

## Out of scope

- Changing the `Ioc` container resolution algorithm itself (`__getattr__` suffix
  rules, importlib scan, factories) — unchanged.
- Renaming files or classes; adding new domains, endpoints, or business features.
- Database schema, migrations, seed SQL — none required (no table changes).
- Real `UserStorage` implementation (still `NotImplementedUserLookupService`).
- `get_current_user` / `helpers/security.py` — unrelated, untouched.
- Frontend / UI — none.

## Acceptance criteria

1. `app/controllers/base_controller.py` defines `BaseController` with
   `__init__(self, ioc: Ioc = Depends(get_ioc))` and `__getattr__` delegating to
   `self._ioc`.
2. `app/services/abstract_service.py` defines `AbstractService` with
   `__init__(self, ioc)` and `__getattr__`.
3. `app/storages/abstract_storage.py` defines `AbstractStorage` with
   `__init__(self, ioc)` and `__getattr__`.
4. `AuthController(BaseController)` exists; routes use
   `Depends(AuthController)` and contain no `Depends(get_ioc)` and no `ioc`
   parameter.
5. `AuthService(AbstractService)` uses `self.X` exclusively — no `self._ioc.` and
   no `ioc.` in the body.
6. `RefreshTokenStorage(AbstractStorage)` and
   `NotImplementedUserLookupService(AbstractService)` use the base `__init__`;
   storage reads `self.redis` rather than a `redis` parameter.
7. No `self._ioc.` or `ioc.` token remains in any controller, service, or storage
   business body (allowed only inside the base classes / `ioc.py`).
8. `python -c "import app.main"` imports cleanly.
9. FastAPI route wiring resolves: `/auth/refresh` returns 401 on an unknown
   token (error-factory path proves the full self-access chain), `/auth/logout`
   returns 204, invalid login body returns 422, `/auth/login` reaches the
   NotImplemented user lookup (proving controller→service→storage self-access).
10. All new/changed code: full type hints, `logging` not `print`, no mutable
    defaults, layer boundaries respected.

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `app/controllers/base_controller.py` | created (`BaseController`) | implementer |
| `app/services/abstract_service.py` | created (`AbstractService`) | implementer |
| `app/storages/abstract_storage.py` | created (`AbstractStorage`) | implementer |
| `app/controllers/auth/router.py` | updated (`AuthController` + thin routes) | implementer |
| `app/services/auth/auth_service.py` | updated (extend, `self.X`) | implementer |
| `app/services/auth/not_implemented_user_lookup_service.py` | updated (extend) | implementer |
| `app/storages/refresh_token_storage.py` | updated (extend, `self.redis`) | implementer |
| `docs/architecture/IOC.md` | updated (base-class pattern sections) | docs-writer |
| `.claude/rules/RULES.md` | updated (controller/service/storage usage) | docs-writer |
| `docs/plans/2026-05-20-ioc-base-class-self-access.md` | this plan; → implemented at end | docs-writer |

## Risks

- **R1 — `__getattr__` recursion before `_ioc` is set.** If `__getattr__` runs
  before `__init__` assigns `self._ioc` (e.g. during unpickling, or framework
  introspection), `getattr(self._ioc, ...)` recurses on the missing `_ioc`.
  Mitigation: guard `if name.startswith("_"): raise AttributeError(name)` in all
  three base `__getattr__` methods (the container already uses this guard).
- **R2 — FastAPI introspection of the controller class.** `Depends(AuthController)`
  makes FastAPI inspect `AuthController.__init__`'s signature to find the nested
  `Depends(get_ioc)`. Since `AuthController` inherits `__init__` from
  `BaseController`, FastAPI must see the inherited signature. This works because
  FastAPI reads `inspect.signature(cls)` which resolves inherited `__init__`.
  Verify in acceptance test 9.
- **R3 — `__getattr__` masking real attribute errors / typos.** A typo like
  `self.AuthServ` would be forwarded to the container and raise
  `IocResolutionError` (an `AttributeError` subclass) with a container message
  rather than a controller-local one. Acceptable: the message still names the bad
  attribute and the suffix rules.
- **R4 — Storage signature change blast radius.** Dropping `redis` from
  `RefreshTokenStorage` methods changes the call contract; all callers are in
  `AuthService` and must be updated in the same change. No other callers exist
  (verified by grep — only `auth_service.py` uses `RefreshTokenStorage`).
- **R5 — Memoization semantics unchanged.** `self.AuthService` resolves through
  `self._ioc`, so per-request memoization in `Ioc._instances` still applies; each
  request builds a fresh `BaseController` with a fresh `Ioc`. No cross-request
  leakage introduced.

## Agent decisions

- **planner:** this plan, no code. Brainstorming bypassed: the task fully
  specifies the target design with concrete code; no open design questions remain.
- **ui-designer:** not required (no UI scope).
- **database:** not required (no schema/migration/seed change).
- **implementer:** owns all three base classes and the four file updates to this
  contract.
- **reviewer:** verify no `self._ioc.`/`ioc.` left in business bodies, base
  `__getattr__` recursion guard present, route wiring works, storage `self.redis`
  switch is consistent with call sites, type hints, layer boundaries.
- **security:** not required — no change to how `tenant_id` is sourced (still
  claims-only via `get_ioc`); no new user-input path into attribute resolution
  (all `self.X` names remain source-code literals). Note for reviewer to confirm.
- **docs-writer:** update `docs/architecture/IOC.md` (Controller/Service/Storage
  usage sections + a Base Classes section), update `.claude/rules/RULES.md`
  controller/service/storage usage guidance, set this plan to `implemented` with a
  "What was built" section.
- **version-control:** commit plan + code + docs together at the end.

## Approval log

- 2026-05-20: plan drafted (`draft`), awaiting user approval. No open questions —
  design is fully specified by the task. Approve to proceed to implementer.
