---
name: api-v2-architecture
description: Create or update backend endpoints following the established Python/FastAPI architecture. Use when adding or changing controllers, requests, services, storages, data, or errors for an endpoint.
---

## When To Use

Use this skill when the task involves:

- a new endpoint
- a change to an existing endpoint
- a new request, service, storage, data, or error class
- API contract updates

## Workflow

1. Determine whether the work is a full endpoint or a single layer.
2. Read the relevant existing endpoint files for the same entity shape — use Warehouses as the default reference (see Required Reading).
3. Follow the established naming and folder rules exactly.
4. Update all affected layers together.
5. Keep the response and validation contract consistent if the API contract changed.
6. If the endpoint adds a new table or persisted domain structure, update `warehouse_full_seed.sql` with both schema and example seed data.
7. If the scope includes DB design decisions, use the database agent output as the DB contract before coding.

## Layers

```
Controller → Request → Service → Storage → Data ↔ Database
                    ↕
                 Mapper (per-request context)
```

Each layer has a single responsibility. Never skip or merge layers.

| Layer | Responsibility |
|---|---|
| Controller | Route requests, return responses, wrap mutations in the transaction helper |
| Request | Validate and normalize all input at the boundary |
| Service | All business logic, coordinates storages |
| Mapper | Per-request context holder (identity, role checks); may lazy-load from Storage |
| Storage | All database access; returns Data / DataCollection / None |
| Data | Entity shape, `from_row` factory, no logic |
| Error | `ApplicationError` subclasses, unique error codes |

## Dependency Injection

The official DI mechanism is the per-request **IoC container** (`app/infrastructure/ioc.py`). There is no manual `Depends(get_xyz_service)` wiring and no injected collaborator constructor lists.

- Resolve collaborators and resources by **class name** through `self.<ClassName>` — the suffix selects the layer:
  - `*Service` → `app/services/{domain}/` → memoized request-scoped instance
  - `*Storage` → `app/storages/` (flat) → memoized request-scoped instance
  - `*Mapper` → `app/mappers/` (flat) → memoized request-scoped instance
  - `*Request` → `app/requests/{domain}/` → `GenericFactory`; call `.get(...)` to construct
  - `*Error` → `app/errors/{domain}/` → `ErrorFactory`; call `.get(...)` to construct, `.target` for the class
- Convention-strict resolution: a resolvable class lives in a module whose file name is the snake_case of the class name. `WarehouseCreateService` → `warehouse_create_service.py`; `WarehouseStorage` → `warehouse_storage.py`; `ActiveUserMapper` → `active_user_mapper.py`.
- Service, storage, and mapper constructors take a single `ioc: Ioc` argument and pull collaborators and resources lazily via `self.<ClassName>` / `self.session` / `self.redis` / `self.settings` / `self.claims`. They never declare `__init__` (they inherit from the abstract base) and never name a field `ioc` or `self._ioc`.
- Resolution names are always literals in source (`self.WarehouseStorage`), never derived from request data. Unknown names raise `IocResolutionError`.

## Controller

- No business logic. No direct database access.
- Extend `BaseController` (`app/controllers/base_controller.py`). Never declare `__init__`; never name a field `ioc` or `self._ioc`.
- Resolve collaborators and resources on demand via `self.<ClassName>` (e.g. `self.WarehouseCreateService`, `self.InvalidCredentialsError.target`).
- Routes stay thin: inject the controller via `ctrl: <Controller> = Depends(<Controller>)` and delegate to a controller method. Routes carry no `ioc` parameter and no `Depends(get_ioc)`.
- Flat-flow: no `try`/`except`. Domain errors (subclasses of `ApplicationError`) raised by services bubble up to the global handler in `app/main.py`, which maps them to the right HTTP status and detail.
- Wrap all mutations using `self.transaction.wrap(self.session, ...)`.
- Read identity only through `self.ActiveUserMapper` (`is_initialized()`, `user_id`, `tenant_id`, `role`, `is_admin()`, `is_manager()`). Never resolve identity in the controller.

## Request

- All validation here, never in services.
- Implemented as typed classes (Pydantic `BaseModel`) with validation at the boundary.
- PATCH requests validate only submitted fields using `model_fields_set`.
- Validated input is trusted downstream — do not re-validate.
- Never re-cast or re-validate values from validated request objects in controllers or services. Treat validated request fields as already normalized to the correct type. If the type or range is wrong, fix the request rules — do not patch it downstream.
- Never trust `tenant_id` or `role` from the request body or query params — they come from verified token claims, never user input.

## Service

- All business logic lives here.
- Extend `AbstractService` (`app/services/abstract_service.py`). Never declare `__init__`; never name a field `ioc` or `self._ioc`.
- Access collaborators and resources via `self.<ClassName>` (e.g. `self.WarehouseStorage`, `self.redis`, `self.settings`, `self.<OtherService>`).
- Never starts transactions. Never accesses the database directly. Uses storages for all reads and writes.
- Prefer create flows shaped like `WarehouseCreateService`: validate business constraints, build the entity `Data` object, pass that object to storage, let storage assign the new id onto it, and return that created object directly.
- For additive relation flows, prefer `AddService` naming over `CreateService` when the operation attaches an existing entity to another existing entity rather than creating a standalone root entity.
- Do not build raw dicts / DB-row dicts in services for normal entity create flows when a matching `Data` class exists.
- Do not re-read an entity immediately after create by default.
- When a delete flow only needs the entity id for checks and deletion, pass the id to the delete service instead of fetching or passing a partial data object.

## Mapper

- Per-request context holder — not a DTO, not a service, not a repository.
- Holds state set once per request (e.g. verified JWT identity) and exposes computed properties and role-check methods.
- May lazy-load related data from Storage, caching the result on the instance.
- Must subclass `AbstractMapper` (`app/mappers/abstract_mapper.py`); lives flat under `app/mappers/`.
- Never opens transactions; never writes to the database directly.
- Access identity (`ActiveUserMapper`) only after verifying `is_initialized()` on public / optional-auth routes.

## Storage

- Only layer that touches the database.
- Extend `AbstractStorage` (`app/storages/abstract_storage.py`). Never declare `__init__`; never name a field `ioc` or `self._ioc`.
- Read request-scoped resources via `self.<resource>` (`self.session`, `self.tenant_id`, `self.redis`). Never accept them as method parameters.
- Every query filters by `tenant_id` — no exceptions. `tenant_id` is read from `self.tenant_id` (sourced from verified JWT claims), never from a method argument.
- Never starts transactions.
- Assigns generated primary keys back to the `Data` object passed in.
- Returns `Data`, `DataCollection`, or `None` — nothing else.

### Standard Read API

- Each storage exposes `get(...)` and `get_partial(...)` by default.
- Use `get_by_id(...)` and `get_by_id_partial(...)` only when the lookup is by one concrete id field for that entity.
- If a lookup uses multiple id fields, name the method explicitly after those fields — `get_by_warehouse_id_and_movement_id(...)` and `get_by_warehouse_id_and_movement_id_partial(...)`. Do not hide a composite lookup behind `get_by_id(...)`.
- Do not leave a storage in a half-custom state. The standard read API is mandatory; entity-specific helpers may only be thin wrappers around it, not replacements.

### Scope

- Keep each storage scoped to its own persisted entity / table set. Each persisted table has its own dedicated storage by default.
- If a storage needs data from another entity, either use the other storage explicitly or make the broader scope intentional and obvious before introducing joins.
- Auxiliary lookup storages (auth, session, token helpers) may stay lookup-oriented when they do not represent a normal endpoint-facing entity read contract, but they still must use explicit naming and must not masquerade as `get_by_id(...)` APIs when the lookup semantics differ.

### Query Order

- Call `_apply_lock(...)` before any `_apply_filters(...)` call.
- Leave a blank line after each `_apply_lock(...)` and `_apply_filters(...)` call before the next statement.

### Consistency

- Keep storage read implementations structurally consistent with peer storages: same query-building flow, locking flow, and `from_row(...)` / `DataCollection` response shaping.
- Aim for conceptual consistency, not copy-paste sameness. The important part is the method surface, naming, lookup semantics, and response shaping — not forcing identical line-by-line internals.
- Composite-key or relation storages are not an exception — they still need a consistent base read shape, but their single-row lookup methods must stay explicit about which ids are used.

## Data

- One class per entity, implemented as a Python `dataclass`.
- Field names match DB column names exactly.
- `from_row` is a `@classmethod` factory. No business logic; only field/type plumbing (`from_row`, `fix_type`, `to_dict`).
- When a DB result row already has the needed shape, pass it directly into `from_row(...)` instead of casting it to a dict first.
- Entity Data classes that need type coercion, a field whitelist, expanded child fields, or `to_dict()` serialization extend `AbstractData` (`app/data/abstract_data.py`): declare `FIELDS = {field: type_token}` with tokens `int` / `float` / `string` / `bool` / `datetime` / `expanded`. `expanded` fields hold nested children (`field(default_factory=list)`), are not read from the row, and are filled by `DataCollection.expand_property`.
- Auth identity Data (`AuthUser`, `TokenData`) stays a plain `@dataclass` — no expanded fields, and `password_hash` must never be serialized via `to_dict()`.
- A `DataCollection[T]` (`app/data/data_collection.py`) wraps `list[T]` and adds `expand_property`, `extract_property_values`, `extract_property_values_as_keys`, `group_by_property`, `to_list`, `to_dicts`. Use it as the storage collection return type and for in-memory parent->children expand.

## Error

- Extend `ApplicationError` (`app/errors/application_error.py`); one file per error, under `app/errors/{domain}/`.
- Set the error contract via class attributes: `http_status`, `detail`, and optionally `headers`. There is no `self.exception` field and no central `ErrorDefinitions` registry — the attributes are the source of truth, and the global handler in `app/main.py` builds the response from them.
- Error codes are unique across the system.
- Resolve and raise via the IoC `*Error` convention: `self.<Name>Error` returns an `ErrorFactory`; use `.get(...)` to construct and `.target` for the class.

## Collection Filter And Expand Rules

- Filters in collection endpoints use plural id fields: `warehouse_ids`, `movement_ids`, `user_ids`. Do not add single-id collection filters such as `warehouse_id` or `movement_id`.
- Treat `expand` as collection-only behavior. Do not support `expand` on `GET` endpoints with a concrete path id such as `GET /api/warehouses/{id}` or `GET /api/users/{id}`.
- Do not use filter request / service patterns for endpoints that already have an id in the URL path. For `GET` endpoints with a concrete path id, read directly from storage instead of routing through collection filter services.

### Expand Mechanics

- Validate `?expand=` with `validate_expand(raw, expandable)` (`app/helpers/expand_validator.py`); never trust the raw string.
- Each endpoint that supports expand declares its own `expandable` spec `{resource: [allowed_field, ...]}`. Wire it via `expand_dependency(expandable)` (a FastAPI `Query`-bound dependency).
- `validate_expand` rejects resources not in the spec and fields not in `expandable[resource]`, expands a bracket-less resource to all allowed fields, returns `{}` for `None` / empty, and raises `RequestValidationError` (unified `V001` 422 envelope) on any violation.
- The `expandable` whitelist is the trust boundary. Use only the validated output as response keys or to choose which child storages to load. Never pass un-whitelisted resource / field names into `getattr`, dynamic resolution, or SQL identifiers.
- Service expand flow (single-level parent->children): load children → `children.group_by_property(child_fk)` → `parents.expand_property(resource, parent_key, grouped)`. The expanded field must be declared `expanded` in the parent Data's `FIELDS`.

## Transactions

- Wrap all mutating controller actions in `self.transaction.wrap(self.session, ...)`.
- Services never start transactions; storages operate within the transaction the controller opened.
- Use `PUT` for idempotent add / attach operations that target a specific parent resource in the URL.
- Multi-tenancy: PostgreSQL RLS is the second enforcement layer behind the per-query `tenant_id` filter. Both must hold.

## Naming

- Files and modules: `snake_case.py`. Classes: `PascalCase`. Functions / methods: `snake_case`. Constants: `UPPER_SNAKE_CASE`. Type hints required on all signatures and class fields.
- Keep entity-specific file suffixes intact: `_controller`-less controller files (see below), `_request.py`, `_service.py`, `_storage.py`, `_data.py`, `_data_collection.py`, `_error.py`.
- For parent-child APIs, prefer nested endpoints such as `warehouses/{warehouse_id}/movements` and `warehouses/{warehouse_id}/movements/{movement_id}` instead of a mixed top-level relation endpoint.
- Prefer explicit local variable names in controllers and services. Avoid generic names like `existing`; name the entity directly — `existing_warehouse`, `existing_movement`.
- Keep a blank line between the last method in a class and the end of the class body.
- Keep all file types structurally and architecturally consistent with their peers unless there is an explicit reason not to.

### Controller File Naming Convention

The controller file name is derived from the URL folder path under `app/controllers/`:

- path separators (`/`) become `_`
- `{param}` segments have their braces stripped (the word is kept)
- the result is `snake_case`

The class name is the PascalCase of that path plus the `Controller` suffix.

| URL folder path | Controller file | Controller class |
|---|---|---|
| `controllers/auth/` | `auth.py` | `AuthController` |
| `controllers/warehouses/` | `warehouses.py` | `WarehousesController` |
| `controllers/warehouses/{warehouse_id}/` | `warehouses_warehouse_id.py` | `WarehousesWarehouseIdController` |
| `controllers/warehouses/{warehouse_id}/movements/` | `warehouses_warehouse_id_movements.py` | `WarehousesWarehouseIdMovementsController` |

CloudSale equivalent: `controllers/Products/Products.php` and `controllers/Products/{id}/Products_ID.php`.

## Required Reading

At minimum, inspect one complete existing entity flow before implementing. Use `Warehouses` as the default reference (full list in `references/reference-files.md`):

- `app/controllers/warehouses/warehouses.py`
- `app/controllers/warehouses/warehouses_id.py`
- `app/requests/warehouse/warehouse_create_request.py`
- `app/requests/warehouse/warehouse_update_request.py`
- `app/requests/warehouse/warehouse_collection_filter_request.py`
- `app/services/warehouse/warehouse_create_service.py`
- `app/services/warehouse/warehouse_update_service.py`
- `app/services/warehouse/warehouse_delete_service.py`
- `app/services/warehouse/warehouse_collection_filter_service.py`
- `app/storages/warehouse_storage.py`
- `app/data/warehouse_data.py`
- `app/data/warehouse_data_collection.py`

If the Warehouses flow does not exist yet, the closest complete reference in the repo is the auth flow (`app/controllers/auth/auth.py`, `app/services/auth/`, `app/storages/`, `app/errors/auth/`) for the IoC, flat-flow controller, and error-class shape.

## Reference Shape

Use `Warehouses` as the standard reference for a normal endpoint. The five standard actions and their controller methods:

| Action | Route | Controller method | Layer flow |
|---|---|---|---|
| Collection read | `GET /warehouses` | `WarehousesController.get` | request (filter) → `WarehouseCollectionFilterService` → `WarehouseStorage.get` → `DataCollection` |
| Create | `POST /warehouses` | `WarehousesController.post` | `WarehouseCreateRequest` → `WarehouseCreateService` → `WarehouseStorage` (assigns id) → created `WarehouseData` |
| Item read | `GET /warehouses/{id}` | `WarehousesWarehouseIdController.get` | read directly via `WarehouseStorage.get_by_id` (no filter service, no expand) |
| Patch | `PATCH /warehouses/{id}` | `WarehousesWarehouseIdController.patch` | `WarehouseUpdateRequest` (only `model_fields_set`) → `WarehouseUpdateService` → `WarehouseStorage` |
| Delete | `DELETE /warehouses/{id}` | `WarehousesWarehouseIdController.delete` | id-only → `WarehouseDeleteService` → `WarehouseStorage` |

All mutating actions (`post`, `patch`, `delete`) are wrapped in `self.transaction.wrap(self.session, ...)`.

## References

Deeper dives (the rules above are consolidated from these; the sub-files remain as detail):

- **Layer rules — controller, request, service, data** → `references/layers.md`
- **Storage API shape and consistency rules** → `references/storage.md`
- **Relation and filter endpoint rules** → `references/relations.md`
- **Warehouses reference files** → `references/reference-files.md`

## Notes

- Keep this skill focused on endpoint implementation shape.
- For new endpoint-backed persistence, `warehouse_full_seed.sql` is part of the required delivery, not optional follow-up.
