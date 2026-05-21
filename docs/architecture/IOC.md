# IoC Container

## Definition

`Ioc` is the per-request Inversion-of-Control container. Source: `app/infrastructure/ioc.py`. It is the official and only dependency-injection mechanism of the Warehouse backend.

## Scope

- Lifetime: one instance per HTTP request.
- Construction: via the `get_ioc` FastAPI dependency only.
- Never an application-level singleton. Never cached at module level. Never reused across requests.

## Carried State

| Attribute | Type | Source | Notes |
|---|---|---|---|
| `session` | `AsyncSession` | request DB scope | property; raises `IocResolutionError` if no session bound |
| `claims` | `TokenData \| None` | `request.state.token_data`, set by `AuthMiddleware` | full claims object established by the auth middleware via a hard channel split by `User-Agent` (browser ⇒ JWT bearer only, non-browser/missing ⇒ API key only); `get_ioc` reads it from `request.state` and never decodes a token itself; `None` for public/unauthenticated routes; never from body/query; no setter |
| `tenant_id` | `str \| None` | derived from `claims.tenant_id` | `None` for public routes; never from body/query; backward-compatible property |
| `redis` | `Redis` | `get_redis` provider | request-scoped client |
| `settings` | `Settings` | `get_settings` provider | application settings |
| `transaction` | `TransactionHelper` | container | memoized per request |

## Resolution Rules

The container resolves classes by **class name** via `__getattr__`. The class-name suffix selects the layer.

| Suffix | Package root | Nesting | Returns |
|---|---|---|---|
| `*Service` | `app.services` | nested by domain | instance (memoized) |
| `*Storage` | `app.storages` | flat | instance (memoized) |
| `*Mapper` | `app.mappers` | flat | instance (memoized) |
| `*Request` | `app.requests` | nested by domain | `GenericFactory` |
| `*Error` | `app.errors` | nested by domain | `ErrorFactory` |

- Unknown suffix → `IocResolutionError`.
- Known suffix, no matching module/class → `IocResolutionError`.
- `IocResolutionError` subclasses `AttributeError`. Never returns `None`.
- `*Mapper` lifetime: request-scoped memoized instance, same as `*Service`/`*Storage`. Constructor takes `ioc: Ioc`.

## Path Convention (Strategy B, convention-strict)

A resolvable class lives in a module whose file name is the snake_case of the class name. The resolver scans the layer package recursively, so domain nesting is not encoded in the class name.

| Class | Module file | Resolved path |
|---|---|---|
| `AuthService` | `auth_service.py` | `app/services/auth/auth_service.py` |
| `UserLookupService` | `user_lookup_service.py` | `app/services/auth/user_lookup_service.py` |
| `RefreshTokenStorage` | `refresh_token_storage.py` | `app/storages/refresh_token_storage.py` |
| `AbstractMapper` | `abstract_mapper.py` | `app/mappers/abstract_mapper.py` |
| `ActiveUserMapper` | `active_user_mapper.py` | `app/mappers/active_user_mapper.py` |
| `LoginRequest` | `login_request.py` | `app/requests/auth/login_request.py` |
| `RefreshRequest` | `refresh_request.py` | `app/requests/auth/refresh_request.py` |
| `LogoutRequest` | `logout_request.py` | `app/requests/auth/logout_request.py` |
| `InvalidCredentialsError` | `invalid_credentials_error.py` | `app/errors/auth/invalid_credentials_error.py` |
| `InvalidTokenError` | `invalid_token_error.py` | `app/errors/auth/invalid_token_error.py` |
| `ExpiredTokenError` | `expired_token_error.py` | `app/errors/auth/expired_token_error.py` |
| `UnauthenticatedError` | `unauthenticated_error.py` | `app/errors/auth/unauthenticated_error.py` |

`*Mapper` uses a flat namespace (`app/mappers/`). Nesting depth is 1 (no subdomain folders). The recursive scanner still discovers classes correctly.

snake_case conversion: insert `_` before every uppercase letter that is not the first character, then lowercase. `AuthService` → `auth_service`. `RefreshTokenStorage` → `refresh_token_storage`.

## Instantiation Contract

- `*Service`, `*Storage`, and `*Mapper` constructors take exactly one argument: `ioc: Ioc`.
- Concrete services extend `AbstractService` (`app/services/abstract_service.py`); concrete storages extend `AbstractStorage` (`app/storages/abstract_storage.py`). The base class owns `__init__(self, ioc)` and stores `self._ioc = ioc`. Concrete classes do not declare their own `__init__`.
- Collaborators and resources are pulled lazily inside methods via `self.X` (delegated to `self._ioc` by the base `__getattr__`): `self.RefreshTokenStorage`, `self.session`, `self.redis`, `self.settings`, `self.<OtherService>`, `self.claims`. Business code never names `ioc` or `self._ioc`.
- No injected collaborator parameter lists. No `Depends(get_xyz_service)` chains.
- Resolved `*Service` / `*Storage` / `*Mapper` instances are memoized for the lifetime of one `Ioc` (same instance returned on repeated access within a request).

## Factory Contract

- `*Request` resolves to a `GenericFactory`. `ioc.LoginRequest.get(email=..., password=...)` constructs the instance. `ioc.LoginRequest.target` is the class.
- `*Error` resolves to an `ErrorFactory`. `ioc.InvalidCredentialsError.get("message")` constructs the error. `ioc.InvalidCredentialsError.target` is the class.
- Request models are normally constructed by FastAPI from the request body; the factory exists for explicit construction and symmetry with the CloudSale PHP pattern.
- Errors are raised, not injected: in business code `raise self.InvalidTokenError.get("...")`.
- Controllers catch container errors by class: `except self.InvalidTokenError.target:`.

## Base Classes (self.X Access)

The `Ioc` container is invisible to business code. Controllers, services, and storages access collaborators and request-scoped resources through `self.X`, mirroring the CloudSale PHP `$this->AuthService` ergonomics. Three base classes provide this:

| Base class | File | Used by | Carries `Depends(get_ioc)` |
|---|---|---|---|
| `BaseController` | `app/controllers/base_controller.py` | controllers | yes |
| `AbstractService` | `app/services/abstract_service.py` | services | no |
| `AbstractStorage` | `app/storages/abstract_storage.py` | storages | no |

Mechanism:

1. Each base class defines `__init__(self, ioc)` storing `self._ioc = ioc`. `BaseController.__init__` declares `ioc: Ioc = Depends(get_ioc)` so the FastAPI dependency lives only in the base class. `AbstractService` / `AbstractStorage` take a plain `ioc: Ioc` (supplied by the IoC resolver when it instantiates the class via `target(self)`).
2. Each base class defines `__getattr__(self, name)` that delegates missing-attribute lookups to `getattr(self._ioc, name)`.
3. `__getattr__` guards leading-underscore names: `if name.startswith("_"): raise AttributeError(name)`. This prevents infinite recursion before `_ioc` is assigned and stops dunder/introspection lookups (e.g. `__deepcopy__`) from triggering IoC resolution.

Constraints:

- Business code (controllers, services, storages) must never name `ioc` or `self._ioc`. The tokens `ioc.` and `self._ioc.` appear only inside the base classes and `app/infrastructure/ioc.py`.
- A typo such as `self.AuthServ` is forwarded to the container and raises `IocResolutionError` (an `AttributeError` subclass) naming the bad attribute and the suffix rules.

## Caching

- `_CLASS_CACHE` is a process-level cache mapping class name → resolved class object. It caches **types only**, never instances and never sessions. Types are immutable for the process lifetime.
- `_instances` is per-`Ioc` and holds live instances. It is request-scoped and garbage-collected with the container.

## Controller Usage

Controllers are classes extending `BaseController`. The `Depends(get_ioc)` injection lives in the base class, so routes inject the controller class itself via `Depends(<Controller>)` and stay thin.

```python
from app.controllers.base_controller import BaseController

class AuthController(BaseController):
    async def login(self, body: LoginRequest) -> dict:
        try:
            return await self.AuthService.login(email=body.email, password=body.password)
        except self.InvalidCredentialsError.target:
            raise HTTPException(status_code=401, detail="Invalid credentials")

@router.post("/login")
async def login(body: LoginRequest, ctrl: AuthController = Depends(AuthController)) -> dict:
    return await ctrl.login(body)
```

- Routes declare no `ioc` parameter and no `Depends(get_ioc)`. FastAPI resolves `BaseController.__init__`'s inherited `ioc: Ioc = Depends(get_ioc)` transitively when it instantiates the controller for `Depends(AuthController)`.
- Wrap mutations: `await self.transaction.wrap(self.session, service_method, ...)`.

## Service Usage

Services extend `AbstractService` and access everything through `self.X`. No `__init__` is declared on the concrete class.

```python
from app.services.abstract_service import AbstractService

class AuthService(AbstractService):
    async def refresh(self, refresh_token: str) -> dict:
        refresh_storage = self.RefreshTokenStorage
        settings = self.settings
        ...
        raise self.InvalidTokenError.get("Refresh token is invalid or has expired")
```

## Storage Usage

Storages extend `AbstractStorage` and read request-scoped resources through `self.X` (`self.session`, `self.tenant_id`, `self.redis`). Resources are not passed as method parameters.

```python
from app.storages.abstract_storage import AbstractStorage

class RefreshTokenStorage(AbstractStorage):
    async def delete(self, token: str) -> None:
        await self.redis.delete(f"refresh:{token}")
```

## Adding a New Dependency

1. Create the class in the correct layer package with the matching file name (snake_case of the class name) and the correct suffix.
   - Service: `app/services/<domain>/<thing>_service.py` exporting `<Thing>Service`.
   - Storage: `app/storages/<thing>_storage.py` exporting `<Thing>Storage`.
   - Request: `app/requests/<domain>/<action>_request.py` exporting `<Action>Request`.
   - Error: `app/errors/<domain>/<thing>_error.py` exporting `<Thing>Error`.
2. For services extend `AbstractService`; for storages extend `AbstractStorage`. Do not declare `__init__` — the base class owns it.
3. Resolve collaborators where needed via `self.<ClassName>` inside methods. No registration step is required — resolution is by convention.

## Security Properties

- `claims` (full `TokenData`) and `tenant_id` are established once per request by `AuthMiddleware` (`app/infrastructure/auth_middleware.py`), which runs before any route handler and attaches the verified `TokenData` to `request.state.token_data`. `get_ioc` reads that value from `request.state` and never decodes a token itself, so the middleware is the single source of identity. Identity is sourced only from verified JWT claims or, for external clients, from the user record resolved by `ApiKeyStorage` — never from request body or query parameters — and has no setter.
- `ActiveUserMapper` identity properties (`user_id`, `tenant_id`, `role`) raise `UnauthenticatedError` when `claims` is `None`. Do not access identity properties on public routes without guarding with `is_initialized()` first.
- Container attribute names are always literals in source code. No code path passes user input into `getattr(ioc, ...)` or `ioc.<x>`. The dynamic `importlib` resolution therefore cannot be driven by user input.
- Package scanning is bounded to the five fixed roots (`app.services`, `app.storages`, `app.mappers`, `app.requests`, `app.errors`). Resolution cannot import modules outside `app.*`.
- The container is request-scoped; the session and per-request instances are never shared across requests. Only immutable class objects are cached at process level.
- `get_ioc` is not an authentication gate. It only reads the identity that `AuthMiddleware` established on `request.state`. Authenticated routes must still enforce auth with `get_current_user` (or an equivalent dependency) in addition to obtaining the container. The middleware itself stays non-blocking on the browser/JWT channel (a malformed/expired/absent bearer is treated as anonymous so public routes keep working); the one exception is the machine/API-key channel, where a *presented* API key that cannot be resolved returns 401 immediately rather than downgrading to anonymous.

## Error Reference

| Error | Condition | Type |
|---|---|---|
| `IocResolutionError` | requested name has no known suffix | `AttributeError` subclass |
| `IocResolutionError` | known suffix but no module/class found | `AttributeError` subclass |
| `IocResolutionError` | `ioc.session` accessed when no session is bound | `AttributeError` subclass |
