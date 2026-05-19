# Relation and Filter Endpoint Rules

## Collection Filter Rules

- Filters in collection endpoints use plural id fields: `warehouse_ids`, `movement_ids`, `user_ids`.
- Do not add single-id collection filters such as `warehouse_id` or `movement_id`.
- Treat `expand` as collection-only behavior. Do not support `expand` on `GET` endpoints with a concrete path id such as `GET /api/warehouses/{id}` or `GET /api/users/{id}`.
- Do not use filter request/service patterns for endpoints that already have an id in the URL path.
- For `GET` endpoints with a concrete path id, read directly from storage instead of routing through collection filter services.

## Reference Shape — Warehouses

The `Warehouses` entity is the standard reference for a normal endpoint:

| Action | Route |
|---|---|
| Collection read | `GET /warehouses` |
| Create | `POST /warehouses` |
| Item read | `GET /warehouses/{id}` |
| Patch | `PATCH /warehouses/{id}` |
| Delete | `DELETE /warehouses/{id}` |
