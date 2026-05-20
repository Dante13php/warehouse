# Warehouse Rules

## Product

Warehouse is warehouse management software. It covers:

- **Warehouses** — managing multiple warehouse locations and their stock
- **Production** — manufacturing processes that consume raw materials and produce finished goods
- **Sales** — sales orders and customer-facing transactions
- **Inventory** — stock tracking, inventory counts, adjustments, and movements between locations

Every feature should be evaluated against these four business areas. When adding new entities or endpoints, identify which area they belong to and follow the domain language from `docs/product/DOMAIN_GLOSSARY.md`.

## Backend

### Stack

- Python 3.12+
- FastAPI (async) — HTTP routing and request handling
- SQLAlchemy (async ORM + Core) — database access; ORM for CRUD, Core for complex queries and reporting
- asyncpg — async PostgreSQL driver
- Alembic — database migrations
- Redis — caching, rate limiting, refresh token storage
- ARQ — async background job processing (inventory recalc, reports, email)
- JWT (stateless) — authentication; tenant identity and role travel in the token claims
- PgBouncer — connection pooling in front of PostgreSQL
- PostgreSQL — primary database with Row-Level Security (RLS) enforcing tenant isolation

### Layers

```
Controller → Request → Service → Storage → Data ↔ Database
                    ↕
                 Mapper (per-request context)
```

| Layer | Responsibility |
|---|---|
| Controller | Route requests, return responses, wrap mutations in TransactionHelper |
| Request | Validate and normalize all input at the boundary |
| Service | All business logic, coordinates storages |
| Mapper | Per-request context holder (identity, role checks); may lazy-load from Storage |
| Storage | All database access, returns Data / DataCollection / None |
| Data | Entity shape, from_row factory, no logic |
| Error | ApplicationError subclasses, unique error codes |

### Layer Rules

**Controller**
- No business logic
- No direct database access
- Extend `BaseController` (`app/controllers/base_controller.py`); never declare `__init__` and never name `ioc` or `self._ioc`
- Resolve collaborators and resources on demand via `self.<ClassName>` (e.g. `self.AuthService`, `self.InvalidCredentialsError.target`)
- Routes stay thin: inject the controller via `ctrl: <Controller> = Depends(<Controller>)` and delegate to a controller method; routes carry no `ioc` parameter and no `Depends(get_ioc)`
- Wrap all mutations using `self.transaction.wrap(self.session, ...)`

**Request**
- All validation here, never in services
- PATCH requests validate only submitted fields using `model_fields_set`
- Validated input is trusted downstream — do not re-validate
- Implemented as typed classes with validation at the boundary

**Service**
- All business logic lives here
- Extend `AbstractService` (`app/services/abstract_service.py`); never declare `__init__` and never name `ioc` or `self._ioc`
- Access collaborators and resources via `self.<ClassName>` (e.g. `self.UserStorage`, `self.redis`, `self.settings`, `self.<OtherService>`)
- Never starts transactions
- Never accesses database directly
- Uses storages for all reads and writes

**Mapper**
- Per-request context holder — not a DTO, not a service, not a repository
- Holds state set once per request (e.g. verified JWT identity) and exposes computed properties and role-check methods
- May lazy-load related data from Storage, caching the result on the instance
- Resolved by IoC via the `*Mapper` suffix from the flat `app/mappers/` package; instantiated and memoized per request
- Must subclass `AbstractMapper` (`app/mappers/abstract_mapper.py`)
- Never opens transactions; never writes to the database directly
- Access identity (`ActiveUserMapper`) only after verifying `is_initialized()` on public/optional-auth routes

**Storage**
- Only layer that touches the database
- Extend `AbstractStorage` (`app/storages/abstract_storage.py`); never declare `__init__` and never name `ioc` or `self._ioc`
- Read request-scoped resources via `self.<resource>` (`self.session`, `self.tenant_id`, `self.redis`); never accept them as method parameters
- Never starts transactions
- Assigns generated primary keys back to the Data object passed in
- Returns Data, DataCollection, or None — nothing else

**Data**
- One class per entity
- Implemented as Python `dataclass`
- Field names match DB column names exactly
- `from_row` is a `@classmethod` factory
- No business logic; field/type plumbing only (`from_row`, `fix_type`, `to_dict`) — no domain logic
- Entity Data classes that need type coercion, a field whitelist, expanded child fields, or `to_dict()` serialization extend `AbstractData` (`app/data/abstract_data.py`)
- Auth identity Data (`AuthUser`, `TokenData`) stays a plain `@dataclass` — no expanded fields, and `password_hash` must never be serialized via `to_dict()`

**AbstractData** (`app/data/abstract_data.py`)
- Base mixin for `@dataclass` Data classes; field storage stays the dataclass mechanism (no shadow object)
- `FIELDS: ClassVar[dict[str, str]]` — subclass declares `{field_name: type_token}`; it is the authoritative field whitelist and the source for type coercion
- Type tokens: `int`, `float`, `string`, `bool`, `datetime`, `expanded` (module constants `INT`, `FLOAT`, `STRING`, `BOOL`, `DATETIME`, `EXPANDED`)
- `expanded` marks list-valued nested child fields; declare them `field(default_factory=list)`; they are NOT read from the DB row by the default `from_row` (default `[]`) and are populated later by `DataCollection.expand_property`
- `from_row(cls, row)` maps `FIELDS` keys and applies `fix_type` per field; subclasses may override
- `fix_type(token, value)`: `None` passes through; primitives cast; `datetime` -> tz-aware UTC; `expanded`/unknown -> value unchanged
- Field guard: `__setattr__` rejects writes to names not in `FIELDS` (leading-underscore/dunder allowed)
- `to_dict()` returns the field map in `FIELDS` order (includes `expanded` fields)

**DataCollection** (`app/data/data_collection.py`)
- Generic typed wrapper around `list[T]` (`T = TypeVar("T", bound=AbstractData)`); thin wrapper, not a framework
- Construct with `DataCollection(items=None)` (no mutable default); `add(item)`
- Sequence protocol: `__iter__`, `__len__`, `__getitem__`, `__bool__`
- `expand_property(expanded_property, group_key_property, grouped_values)` — attaches grouped children onto each parent: `item.<expanded_property> = grouped_values.get(item.<group_key_property>, [])` (missing key -> `[]`); single-level parent->children only
- `extract_property_values(name)`, `extract_property_values_as_keys(name)`, `group_by_property(name)`
- `to_list()`, `to_dicts()` for response shaping
- Sorting uses `sorted(collection, key=...)` — no sorter methods on the collection

**Expand pattern** (`app/helpers/expand_validator.py`)
- `?expand=` is user input; the per-endpoint `expandable` spec `{resource: [allowed_field, ...]}` is the trust boundary
- `validate_expand(raw, expandable) -> dict[str, list[str]]` parses `resource[f1,f2],other` and whitelists it: rejects resources not in `expandable`, rejects fields not in `expandable[resource]`, expands a bracket-less resource to all `expandable[resource]` fields, returns `{}` for `None`/empty
- Any malformed input or whitelist violation raises `RequestValidationError`, routed through the unified `V001` 422 envelope
- `expand_dependency(expandable)` returns a FastAPI `Query`-bound dependency for controllers
- Never pass un-whitelisted resource/field names into `getattr`, dynamic class resolution, or SQL identifiers — only the validated output is safe to use as response keys or to select which child storages to load
- Service usage: `result = validate_expand(...)`; `if "products" in result: load children, group_by_property(fk), collection.expand_property("products", parent_key, grouped)`

**Error**
- Extend `ApplicationError`
- Use `ErrorDefinitions` for message text
- Error codes are unique across the system

### Naming Conventions

- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions and methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Type hints are required on all function signatures and class fields

### Database

- New tables require `warehouse_full_seed.sql` updates with schema and seed data
- Transactions: controller wraps, service never starts, storage operates within
- Indexes based on documented access patterns only — no speculative optimization
- Datetime serialization: ISO 8601 UTC — `2026-03-01T14:30:00Z`

### Multi-Tenancy

- Every table has a `tenant_id` column
- Every Storage query filters by `tenant_id` — no exceptions
- PostgreSQL RLS is enabled as a second enforcement layer
- `tenant_id` is resolved from the JWT claims at the request boundary and passed through the service and storage layers — never derived from user input
- Cross-tenant data access is only possible through an explicit admin context, not through normal service calls

### Authentication

- JWT tokens are stateless and short-lived (15–60 minutes)
- Refresh tokens are stored in Redis and are revocable
- Token claims carry: `sub` (user id), `tenant_id`, `role`, `exp`
- Identity is established once per request in `AuthMiddleware` (`app/infrastructure/auth_middleware.py`), which runs before any controller and attaches a verified `TokenData` to `request.state.token_data`. `get_ioc` reads that value; it never decodes a token itself.
- The middleware has two strategies, tried in precedence order: **JWT bearer** first (UI/refresh-token sessions), then **API key** (external API clients, via `ApiKeyStorage` resolving the configured `api_key_header`). JWT wins when both are present.
- A malformed/expired JWT is treated as anonymous so public routes still work; routes that require auth enforce 401 via `get_current_user`. A *presented* API key that cannot be resolved returns 401 immediately — presenting a credential that fails never grants anonymous access.
- Controllers contain no auth/identity-resolution logic. They read identity only through `self.ActiveUserMapper` (`is_initialized()`, `user_id`, `tenant_id`, `role`, `is_admin()`, `is_manager()`); `ActiveUserMapper` is the single read surface for request identity.
- Never trust `tenant_id` or `role` from request body or query params — always read from verified token claims (or the API-key lookup result)

### Dependency Injection

The official DI mechanism is the per-request **IoC container** (`app/infrastructure/ioc.py`). Full specification: `docs/architecture/IOC.md`.

- One `Ioc` instance is created per HTTP request via the `get_ioc` FastAPI dependency. It is request-scoped — never an app-level singleton, never cached at module level.
- The container carries the request's `session` (`AsyncSession | None`), `claims` (`TokenData | None`, full verified JWT claims), `tenant_id` (`str | None`, derived from `claims`), `redis`, and `settings`. All identity values are sourced exclusively from verified JWT claims; never from request body or query params.
- Dependencies are resolved by **class name** through `__getattr__`, using a suffix → layer convention:
  - `*Service` → `app.services` (nested by domain) → memoized request-scoped instance
  - `*Storage` → `app.storages` (flat) → memoized request-scoped instance
  - `*Mapper` → `app.mappers` (flat) → memoized request-scoped instance
  - `*Request` → `app.requests` (nested by domain) → `GenericFactory`; call `.get(...)` to construct
  - `*Error` → `app.errors` (nested by domain) → `ErrorFactory`; call `.get(...)` to construct, `.target` for the class
- Resolution is **convention-strict (Strategy B)**: a resolvable class lives in a module whose file name is the snake_case of the class name. `AuthService` → `auth_service.py`; `RefreshTokenStorage` → `refresh_token_storage.py`; `ActiveUserMapper` → `active_user_mapper.py`; `InvalidCredentialsError` → `invalid_credentials_error.py`.
- Service, storage, and mapper constructors take a single argument `ioc: Ioc` and pull collaborators and resources lazily (`self._ioc.RefreshTokenStorage`, `self._ioc.session`, `self._ioc.redis`, `self._ioc.settings`, `self._ioc.claims`). No injected collaborator parameter lists.
- `get_ioc` is the only `Depends` controllers use. It bootstraps the container by reading the identity that `AuthMiddleware` placed on `request.state`; it does not decode tokens and is not an authentication gate — authenticated routes must still enforce auth with `get_current_user` (or equivalent).
- Resolution names are always literals in source (`ioc.AuthService`); never derive a container attribute name from request data.
- Unknown names raise `IocResolutionError` (an `AttributeError` subclass) — never a silent `None`.

### Anti-Patterns

❌ Manager / Repository pattern — use Storage
❌ Manual DI wiring — no `Depends(get_xyz_service)` chains, no injected collaborator constructor lists; resolve through the IoC container (see Dependency Injection)
❌ Facade — expose layers directly
❌ Hidden layers — all layers explicit in folder structure
❌ DI in abstract classes — keep abstract classes pure
❌ Business logic in controllers
❌ DB access outside storages
❌ Speculative optimization
❌ Using `dict` as an entity when a Data class exists
❌ Database access outside of Storage
❌ `print()` for logging — use the `logging` module
❌ Missing type hints on function signatures
❌ Mutable default arguments (`def f(x=[])`)

### Folder Structure

```
app/
  controllers/{domain}/
  requests/{domain}/
  services/{domain}/
  mappers/
  storages/
  data/
    abstract_data.py      # AbstractData base (FIELDS, expanded token, from_row, fix_type, to_dict, field guard)
    data_collection.py    # DataCollection[T] (expand_property, extract/group, to_dicts)
  errors/{domain}/
  helpers/
    expand_validator.py   # validate_expand + expand_dependency (expand whitelisting)
  infrastructure/
main.py
```

`mappers/` is flat (no subdomain folders). All mapper classes live directly under `app/mappers/`.

---

## Frontend

### Stack

- React with Next.js App Router
- TypeScript
- Motion for animations

### Component Rules

- One component per file, named to match the file
- No business logic in components — fetch and transform in server components or hooks
- Props interfaces defined inline above the component, not exported unless shared
- No default exports for shared components — use named exports

### State Management

- Server state: use server components or SWR / React Query — no manual fetch in useEffect unless unavoidable
- Local UI state: useState / useReducer in the component that owns it
- No global client state unless the need is proven — prefer prop drilling or context scoped to a subtree

### Data Fetching

- Fetch in server components when the data is not user-interaction-driven
- Mutations go through API route handlers — never call backend directly from client components
- Always handle loading and error states explicitly

### Styling

- Utility classes (Tailwind) preferred over custom CSS
- No inline styles except for dynamic values that cannot be expressed as classes
- Component-level CSS modules only when Tailwind is insufficient

### Anti-Patterns

❌ useEffect for data fetching when a server component can do it  
❌ Business logic inside JSX  
❌ Prop drilling beyond two levels — use context or composition  
❌ Any component over 200 lines — split it  
❌ Direct DOM manipulation  
❌ Hardcoded strings in UI — use constants or translation keys  

---

## Agent Creation

When creating a new agent file in `.claude/agents/`:

1. **Check for overlap** — read all existing agent files and determine if any existing agent covers the same responsibility. If overlap exists, notify the user and stop. Do not create a duplicate.

2. **Ask for workflow position** — if no overlap exists, show the current orchestrator workflow order and ask the user where the new agent should be placed before writing anything.

3. **Create the agent file** — only after the user confirms no overlap and provides the workflow position.

4. **Update `orchestrator.md`** — add the new agent to Decision Order, Routing Rules, and Agent Responsibilities table at the confirmed position.

These four steps are mandatory in order. Do not skip or reorder them.
