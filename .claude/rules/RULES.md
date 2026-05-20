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
```

| Layer | Responsibility |
|---|---|
| Controller | Route requests, return responses, wrap mutations in TransactionHelper |
| Request | Validate and normalize all input at the boundary |
| Service | All business logic, coordinates storages |
| Storage | All database access, returns Data / DataCollection / None |
| Data | Entity shape, from_row factory, no logic |
| Error | ApplicationError subclasses, unique error codes |

### Layer Rules

**Controller**
- No business logic
- No direct database access
- Obtain all dependencies through the IoC container (`ioc: Ioc = Depends(get_ioc)`); resolve services on demand via `ioc.<ClassName>`
- Wrap all mutations using `ioc.transaction.wrap(ioc.session, ...)`

**Request**
- All validation here, never in services
- PATCH requests validate only submitted fields using `model_fields_set`
- Validated input is trusted downstream — do not re-validate
- Implemented as typed classes with validation at the boundary

**Service**
- All business logic lives here
- Never starts transactions
- Never accesses database directly
- Uses storages for all reads and writes

**Storage**
- Only layer that touches the database
- Never starts transactions
- Assigns generated primary keys back to the Data object passed in
- Returns Data, DataCollection, or None — nothing else

**Data**
- One class per entity
- Implemented as Python `dataclass`
- Field names match DB column names exactly
- `from_row` is a `@classmethod` factory
- No business logic, no methods beyond `__init__` and `from_row`

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
- Token verification happens in middleware — controllers receive an already-verified identity object
- Never trust `tenant_id` or `role` from request body or query params — always read from verified token claims

### Dependency Injection

The official DI mechanism is the per-request **IoC container** (`app/infrastructure/ioc.py`). Full specification: `docs/architecture/IOC.md`.

- One `Ioc` instance is created per HTTP request via the `get_ioc` FastAPI dependency. It is request-scoped — never an app-level singleton, never cached at module level.
- The container carries the request's `session` (`AsyncSession | None`), `tenant_id` (`str | None`, from verified JWT claims only), `redis`, and `settings`.
- Dependencies are resolved by **class name** through `__getattr__`, using a suffix → layer convention:
  - `*Service` → `app.services` (nested by domain) → memoized request-scoped instance
  - `*Storage` → `app.storages` (flat) → memoized request-scoped instance
  - `*Request` → `app.requests` (nested by domain) → `GenericFactory`; call `.get(...)` to construct
  - `*Error` → `app.errors` (nested by domain) → `ErrorFactory`; call `.get(...)` to construct, `.target` for the class
- Resolution is **convention-strict (Strategy B)**: a resolvable class lives in a module whose file name is the snake_case of the class name. `AuthService` → `auth_service.py`; `RefreshTokenStorage` → `refresh_token_storage.py`; `InvalidCredentialsError` → `invalid_credentials_error.py`.
- Service and storage constructors take a single argument `ioc: Ioc` and pull collaborators and resources lazily (`self._ioc.RefreshTokenStorage`, `self._ioc.session`, `self._ioc.redis`, `self._ioc.settings`). No injected collaborator parameter lists.
- `get_ioc` is the only `Depends` controllers use. It bootstraps the container; it is not an authentication gate — authenticated routes must still enforce auth with `get_current_user` (or equivalent).
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
  storages/
  data/
  errors/{domain}/
  helpers/
  infrastructure/
main.py
```

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
