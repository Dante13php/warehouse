# Storage Rules

## Scope

- Keep each storage scoped to its own persisted entity/table set. Each persisted table should have its own dedicated storage.
- If a storage needs data from another entity, either use the other storage explicitly or make the broader scope intentional and obvious before introducing joins.

## Standard Read API

- Each storage must expose `get(...)` and `get_partial(...)` by default.
- Use `get_by_id(...)` and `get_by_id_partial(...)` only when the lookup is by one concrete id field for that entity.
- If a lookup uses multiple id fields, name the method explicitly after those fields — `get_by_bill_id_and_recipe_id(...)` and `get_by_bill_id_and_recipe_id_partial(...)`.
- Do not leave a storage in a half-custom state. The standard read API is mandatory; entity-specific helpers may only be thin wrappers around it, not replacements.

## Query Order

- Call `_apply_lock(...)` before any `_apply_filters(...)` call.
- Leave a blank line after each `_apply_lock(...)` and `_apply_filters(...)` call before the next statement.

## Consistency

- Keep storage read implementations structurally consistent with peer storages: same query-building flow, locking flow, and `from_row(...)` / `from_rows(...)` response shaping.
- Aim for conceptual consistency, not copy-paste sameness. The important part is the method surface, naming, lookup semantics, and response shaping.
- Composite-key or relation storages are not an exception — they still need a consistent base read shape, but their single-row lookup methods must stay explicit about which ids are used.

## Auxiliary Lookups

Auxiliary lookup storages (auth, session, token helpers) may stay lookup-oriented when they do not represent a normal endpoint-facing entity read contract. They still must use explicit naming and must not masquerade as `get_by_id(...)` APIs when the lookup semantics differ.

## Storage Output

- Assigns generated primary keys back to the `Data` object passed in.
- Returns `Data`, `DataCollection`, or `None` — nothing else.
- Never starts transactions.
