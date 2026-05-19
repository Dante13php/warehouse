---
name: api-v2-architecture
description: Create or update backend endpoints following the established Python architecture. Use when adding or changing controllers, requests, services, storages, data, or errors for an endpoint.
---

## When To Use

Use this skill when the task involves:

- a new endpoint
- a change to an existing endpoint
- a new request, service, storage, data, or error class
- API contract updates

## Workflow

1. Determine whether the work is a full endpoint or a single layer.
2. Read the relevant existing endpoint files for the same entity — use Products as the default reference.
3. Follow the established naming and folder rules exactly.
4. Update all affected layers together.
5. Keep the response and validation contract consistent if the API contract changed.
6. If the endpoint adds a new table or persisted domain structure, update `cloudsale_full_seed.sql` with both schema and example seed data.
7. If the scope includes DB design decisions, use the database agent output as the DB contract before coding.

## References

- **Layer rules — controller, request, service, data** → [`${CLAUDE_SKILL_DIR}/references/layers.md`]
- **Storage API shape and consistency rules** → [`${CLAUDE_SKILL_DIR}/references/storage.md`]
- **Bill, relation, and filter endpoint rules** → [`${CLAUDE_SKILL_DIR}/references/relations.md`]
- **Products reference files** → [`${CLAUDE_SKILL_DIR}/references/reference-files.md`]

## Layers

```
Controller → Request → Service → Storage → Data ↔ Database
```

Each layer has a single responsibility. Never skip or merge layers.

## Naming

| Entity | Convention |
|---|---|
| Files and modules | `snake_case` |
| Classes | `PascalCase` |
| File type suffixes | `_service.py`, `_storage.py`, `_data.py`, `_request.py` |
| Parent-child routes | `bills/{bill_id}/recipes/{recipe_id}` |
| Local variables | Explicit (`existing_product`, not `existing`) |
| Class body | Blank line between the last method and the closing of the class body |

## Transactions

- Wrap all mutating controller actions in `transaction_helper.wrap(db, ...)`.
- Services never start transactions.
- Use `PUT` for idempotent add/attach operations targeting a specific parent resource in the URL.

## Errors

- Extend `ApplicationError`. Register error codes in `app/infrastructure/error_definitions.py` and create a new error file.
- Always set `self.exception`. Separate `self.details` from the code above it and from `self.exception` below it with blank lines.

## Notes

- For new endpoint-backed persistence, `cloudsale_full_seed.sql` is part of the required delivery, not optional follow-up.
