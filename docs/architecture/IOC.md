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
| `tenant_id` | `str \| None` | verified JWT claims | `None` for public routes; never from body/query |
| `redis` | `Redis` | `get_redis` provider | request-scoped client |
| `settings` | `Settings` | `get_settings` provider | application settings |
| `transaction` | `TransactionHelper` | container | memoized per request |

## Resolution Rules

The container resolves classes by **class name** via `__getattr__`. The class-name suffix selects the layer.

| Suffix | Package root | Nesting | Returns |
|---|---|---|---|
| `*Service` | `app.services` | nested by domain | instance (memoized) |
| `*Storage` | `app.storages` | flat | instance (memoized) |
| `*Request` | `app.requests` | nested by domain | `GenericFactory` |
| `*Error` | `app.errors` | nested by domain | `ErrorFactory` |

- Unknown suffix → `IocResolutionError`.
- Known suffix, no matching module/class → `IocResolutionError`.
- `IocResolutionError` subclasses `AttributeError`. Never returns `None`.

## Path Convention (Strategy B, convention-strict)

A resolvable class lives in a module whose file name is the snake_case of the class name. The resolver scans the layer package recursively, so domain nesting is not encoded in the class name.

| Class | Module file | Resolved path |
|---|---|---|
| `AuthService` | `auth_service.py` | `app/services/auth/auth_service.py` |
| `NotImplementedUserLookupService` | `not_implemented_user_lookup_service.py` | `app/services/auth/not_implemented_user_lookup_service.py` |
| `RefreshTokenStorage` | `refresh_token_storage.py` | `app/storages/refresh_token_storage.py` |
| `LoginRequest` | `login_request.py` | `app/requests/auth/login_request.py` |
| `RefreshRequest` | `refresh_request.py` | `app/requests/auth/refresh_request.py` |
| `LogoutRequest` | `logout_request.py` | `app/requests/auth/logout_request.py` |
| `InvalidCredentialsError` | `invalid_credentials_error.py` | `app/errors/auth/invalid_credentials_error.py` |
| `InvalidTokenError` | `invalid_token_error.py` | `app/errors/auth/invalid_token_error.py` |
| `ExpiredTokenError` | `expired_token_error.py` | `app/errors/auth/expired_token_error.py` |

snake_case conversion: insert `_` before every uppercase letter that is not the first character, then lowercase. `AuthService` → `auth_service`. `RefreshTokenStorage` → `refresh_token_storage`.

## Instantiation Contract

- `*Service` and `*Storage` constructors take exactly one argument: `ioc: Ioc`.
- The constructor stores `self._ioc = ioc` and pulls collaborators and resources lazily inside methods: `self._ioc.RefreshTokenStorage`, `self._ioc.session`, `self._ioc.redis`, `self._ioc.settings`, `self._ioc.<OtherService>`.
- No injected collaborator parameter lists. No `Depends(get_xyz_service)` chains.
- Resolved `*Service` / `*Storage` instances are memoized for the lifetime of one `Ioc` (same instance returned on repeated access within a request).

## Factory Contract

- `*Request` resolves to a `GenericFactory`. `ioc.LoginRequest.get(email=..., password=...)` constructs the instance. `ioc.LoginRequest.target` is the class.
- `*Error` resolves to an `ErrorFactory`. `ioc.InvalidCredentialsError.get("message")` constructs the error. `ioc.InvalidCredentialsError.target` is the class.
- Request models are normally constructed by FastAPI from the request body; the factory exists for explicit construction and symmetry with the CloudSale PHP pattern.
- Errors are raised, not injected: `raise ioc.InvalidTokenError.get("...")`.
- Controllers catch container errors by class: `except ioc.InvalidTokenError.target:`.

## Caching

- `_CLASS_CACHE` is a process-level cache mapping class name → resolved class object. It caches **types only**, never instances and never sessions. Types are immutable for the process lifetime.
- `_instances` is per-`Ioc` and holds live instances. It is request-scoped and garbage-collected with the container.

## Controller Usage

```python
from app.infrastructure.ioc import Ioc, get_ioc

@router.post("/login")
async def login(body: LoginRequest, ioc: Ioc = Depends(get_ioc)) -> dict:
    try:
        return await ioc.AuthService.login(email=body.email, password=body.password)
    except ioc.InvalidCredentialsError.target:
        raise HTTPException(status_code=401, detail="Invalid credentials")
```

- `get_ioc` is the only `Depends` a controller uses for dependencies.
- Wrap mutations: `await ioc.transaction.wrap(ioc.session, service_method, ...)`.

## Service Usage

```python
class AuthService:
    def __init__(self, ioc: Ioc) -> None:
        self._ioc = ioc

    async def refresh(self, refresh_token: str) -> dict:
        refresh_storage = self._ioc.RefreshTokenStorage
        settings = self._ioc.settings
        redis = self._ioc.redis
        ...
        raise self._ioc.InvalidTokenError.get("Refresh token is invalid or has expired")
```

## Adding a New Dependency

1. Create the class in the correct layer package with the matching file name (snake_case of the class name) and the correct suffix.
   - Service: `app/services/<domain>/<thing>_service.py` exporting `<Thing>Service`.
   - Storage: `app/storages/<thing>_storage.py` exporting `<Thing>Storage`.
   - Request: `app/requests/<domain>/<action>_request.py` exporting `<Action>Request`.
   - Error: `app/errors/<domain>/<thing>_error.py` exporting `<Thing>Error`.
2. For services/storages, accept `ioc: Ioc` in `__init__` and store it.
3. Resolve it where needed via `ioc.<ClassName>`. No registration step is required — resolution is by convention.

## Security Properties

- `tenant_id` is sourced only from verified JWT claims in `get_ioc` (`decode_access_token`). It is never read from request body or query parameters and has no setter.
- Container attribute names are always literals in source code. No code path passes user input into `getattr(ioc, ...)` or `ioc.<x>`. The dynamic `importlib` resolution therefore cannot be driven by user input.
- Package scanning is bounded to the four fixed roots (`app.services`, `app.storages`, `app.requests`, `app.errors`). Resolution cannot import modules outside `app.*`.
- The container is request-scoped; the session and per-request instances are never shared across requests. Only immutable class objects are cached at process level.
- `get_ioc` is not an authentication gate. Authenticated routes must enforce auth with `get_current_user` (or an equivalent dependency) in addition to obtaining the container.

## Error Reference

| Error | Condition | Type |
|---|---|---|
| `IocResolutionError` | requested name has no known suffix | `AttributeError` subclass |
| `IocResolutionError` | known suffix but no module/class found | `AttributeError` subclass |
| `IocResolutionError` | `ioc.session` accessed when no session is bound | `AttributeError` subclass |
