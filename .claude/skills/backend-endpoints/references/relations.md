# Relation and Filter Endpoint Rules

## Collection Filter Rules

- Filters in collection endpoints use plural id fields: `warehouse_ids`, `movement_ids`, `user_ids`.
- Do not add single-id collection filters such as `warehouse_id` or `movement_id`.
- Treat `expand` as collection-only behavior. Do not support `expand` on `GET` endpoints with a concrete path id such as `GET /api/warehouses/{id}` or `GET /api/users/{id}`.
- Do not use filter request/service patterns for endpoints that already have an id in the URL path.
- For `GET` endpoints with a concrete path id, read directly from storage instead of routing through collection filter services.

## Expand Mechanics

- Validate `?expand=` with `validate_expand(raw, expandable)` (`app/helpers/expand_validator.py`); never trust the raw string.
- Each endpoint that supports expand declares its own `expandable` spec `{resource: [allowed_field, ...]}`. Wire it via `expand_dependency(expandable)` (a FastAPI `Query`-bound dependency).
- `validate_expand` rejects resources not in the spec and fields not in `expandable[resource]`, expands a bracket-less resource to all allowed fields, returns `{}` for `None`/empty, and raises `RequestValidationError` (unified `V001` 422 envelope) on any violation.
- The `expandable` whitelist is the trust boundary. Use only the validated output as response keys or to choose which child storages to load. Never pass un-whitelisted resource/field names into `getattr`, dynamic resolution, or SQL identifiers.
- Service expand flow (single-level parent->children): load children -> `children.group_by_property(child_fk)` -> `parents.expand_property(resource, parent_key, grouped)`. The expanded field must be declared `expanded` in the parent Data's `FIELDS` (`app/data/abstract_data.py`); `DataCollection` is in `app/data/data_collection.py`.

## Reference Shape — Warehouses

The `Warehouses` entity is the standard reference for a normal endpoint:

| Action | Route |
|---|---|
| Collection read | `GET /warehouses` |
| Create | `POST /warehouses` |
| Item read | `GET /warehouses/{id}` |
| Patch | `PATCH /warehouses/{id}` |
| Delete | `DELETE /warehouses/{id}` |
