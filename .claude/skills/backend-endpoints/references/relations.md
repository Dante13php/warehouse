# Bill, Relation, and Filter Endpoint Rules

## Collection Filter Rules

- Filters in collection endpoints use plural id fields: `bill_ids`, `recipe_ids`, `user_ids`.
- Do not add single-id collection filters such as `bill_id` or `recipe_id`.
- Treat `expand` as collection-only behavior. Do not support `expand` on `GET` endpoints with a concrete path id such as `GET /api/bills/{id}` or `GET /api/users/{id}`.
- Do not use filter request/service patterns for endpoints that already have an id in the URL path.
- For `GET` endpoints with a concrete path id, read directly from storage instead of routing through collection filter services.

## Reference Shape — Products

The `Products` entity is the standard reference for a normal endpoint:

| Action | Route |
|---|---|
| Collection read | `GET /products` |
| Create | `POST /products` |
| Item read | `GET /products/{id}` |
| Patch | `PATCH /products/{id}` |
| Delete | `DELETE /products/{id}` |
