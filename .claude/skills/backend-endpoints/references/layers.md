# Layer Rules

## Controller

- No business logic. No direct database access.
- Lazy-resolve services on demand via FastAPI `Depends`.
- Wrap all mutations in `transaction_helper.wrap(db, ...)`.

## Request

- All validation here, never in services.
- PATCH requests validate only submitted fields using `model_fields_set`.
- Validated input is trusted downstream — do not re-validate.
- Never re-cast or re-validate values from validated request objects. Fix the request model if the type or range is wrong.
- Implemented as Pydantic `BaseModel` subclasses.

## Service

- All business logic lives here. Never starts transactions. Never accesses the database directly.
- Prefer create flows shaped like `WarehouseCreateService`: validate business constraints, build the entity `Data` object, pass it to storage, let storage assign the new id, and return the created object directly.
- For additive relation flows, prefer `AddService` naming over `CreateService` when the operation attaches an existing entity to another existing entity rather than creating a standalone root entity.
- Do not build raw dicts in services for normal entity create flows when a matching `Data` class exists.
- Do not re-read an entity immediately after create by default.
- When a delete flow only needs the entity id for checks and deletion, pass the id to the delete service instead of fetching or passing a partial data object.

## Data

- One class per entity, implemented as a Python `dataclass`.
- Field names match DB column names exactly.
- `from_row` is a `@classmethod` factory. No business logic; only field/type plumbing (`from_row`, `fix_type`, `to_dict`).
- When a DB result row already has the needed shape, pass it directly into `from_row(...)` instead of casting it first.
- Entity Data classes that need type coercion, a field whitelist, expanded child fields, or `to_dict()` serialization extend `AbstractData` (`app/data/abstract_data.py`): declare `FIELDS = {field: type_token}` with tokens `int`/`float`/`string`/`bool`/`datetime`/`expanded`. `expanded` fields hold nested children (`field(default_factory=list)`), are not read from the row, and are filled by `DataCollection.expand_property`.
- Auth identity Data (`AuthUser`, `TokenData`) stays a plain `@dataclass` — no expanded fields and `password_hash` must never be serialized.
- A `DataCollection[T]` (`app/data/data_collection.py`) wraps `list[T]` and adds `expand_property`, `extract_property_values`, `extract_property_values_as_keys`, `group_by_property`, `to_list`, `to_dicts`. Use it as the storage collection return type and for in-memory parent->children expand.

## Consistency

Keep all file types structurally and architecturally consistent with their peers. Controllers, requests, services, storages, data classes, errors, and related files should follow the same shape, naming, and layering patterns used elsewhere in the repo unless there is an explicit reason not to.
