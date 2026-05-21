# API Endpoints

Reference for implemented HTTP endpoints. Update in place as endpoints change.

## Conventions

- Datetime serialization: ISO 8601 UTC with trailing `Z` (e.g. `2026-03-01T14:30:00Z`).
- Error envelope (domain errors): `{"error": {"detail": "<message>"}}`. HTTP status set by the error class.
- Validation error envelope (422): `{"error": {"code": "V001", "message": "...", "details": [{"loc": [...], "msg": "..."}]}}`.
- `tenant_id` and `role` are always derived from the verified credential (JWT claims or API-key lookup), never from request input.

## Auth channel selection

- Authentication is established by `AuthMiddleware` before any controller runs.
- Hard channel split by `User-Agent`: browser signature ⇒ JWT bearer only; non-browser/missing ⇒ API key (`X-API-Key`) only. The non-selected credential is never consulted.

---

## Auth

### POST /auth/login

- Auth: none.
- Request body: `{ "email": string, "password": string }`.
- Response 200: `{ "access_token": string, "token_type": "bearer", "refresh_token": string }`.
- Errors: `401` invalid credentials.

### POST /auth/refresh

- Auth: none (refresh token in body).
- Request body: `{ "refresh_token": string }`.
- Response 200: `{ "access_token": string, "token_type": "bearer", "refresh_token": string }` (refresh token rotated).
- Errors: `401` invalid or expired refresh token.

### POST /auth/logout

- Auth: none (refresh token in body).
- Request body: `{ "refresh_token": string }`.
- Response 204: no content (refresh token revoked).

---

## Users

Resource: per-tenant `users` table. Every endpoint requires authentication only (route dependency `require_authentication`). No role-based permission gate is applied in this version (planned for a later task). All storage access is scoped to the caller's `tenant_id`.

Database table: `users`.

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGINT` identity PK | Auto-increment integer. |
| `tenant_id` | `UUID NOT NULL` | Tenant scope. |
| `email` | `TEXT NOT NULL` | Unique per tenant: `UNIQUE (tenant_id, email)`. Lowercased at the request boundary. |
| `password_hash` | `TEXT NOT NULL` | bcrypt hash of a numeric PIN. Never returned, never logged. |
| `role` | `user_role` enum | `manager` or `staff`. |
| `created_at` | `TIMESTAMPTZ NOT NULL` | Server default `now()`. |
| `updated_at` | `TIMESTAMPTZ NOT NULL` | Server default `now()`; bumped on update. |

Row-Level Security: enabled and forced on `users` with policy `tenant_isolation` keyed off the `app.tenant_id` session GUC. Shipped permissive-until-GUC-wired (allows the row when the GUC is unset/empty); application-layer `tenant_id` filtering in `UserStorage` is the primary enforcement until the per-request `SET LOCAL` lands with the tenant-routing follow-up.

User object (response shape, `password_hash` excluded):

```json
{
  "id": 1,
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "email": "user@example.com",
  "role": "staff",
  "created_at": "2026-03-01T14:30:00Z",
  "updated_at": "2026-03-01T14:30:00Z"
}
```

Transaction scope: `POST`, `PATCH`, `DELETE` are wrapped in a single transaction (`TransactionHelper.wrap`). `GET` endpoints are read-only.

### GET /users

- Auth: authenticated.
- Request body: none.
- Response 200: array of User objects, ordered by `created_at`, then `id`.

### POST /users

- Auth: authenticated.
- Request body:
  - `email`: string, required. Valid email. Normalized to trimmed lowercase.
  - `password`: string, required. Numeric PIN, digits only, length 6–14.
  - `role`: string, required. One of `manager`, `staff`.
- Response 201: User object.
- Errors:
  - `409` (`UserAlreadyExistsError`): email already exists for this tenant.
  - `422` (`V001`): invalid email / non-digit or out-of-range PIN / invalid role.

### GET /users/{user_id}

- Auth: authenticated.
- Path param: `user_id` integer.
- Response 200: User object.
- Errors: `404` (`UserNotFoundError`): no user with this id in the caller's tenant (cross-tenant ids are not visible).

### PATCH /users/{user_id}

- Auth: authenticated.
- Path param: `user_id` integer.
- Request body (PATCH semantics: only submitted fields are validated and applied):
  - `email`: string, optional. Valid email, normalized lowercase.
  - `password`: string, optional. Numeric PIN, digits only, length 6–14.
  - `role`: string, optional. One of `manager`, `staff`.
- Response 200: updated User object.
- Errors:
  - `404` (`UserNotFoundError`): target user not found in the caller's tenant.
  - `409` (`UserAlreadyExistsError`): submitted email already used by another user in this tenant.
  - `422` (`V001`): invalid submitted field.

### DELETE /users/{user_id}

- Auth: authenticated.
- Path param: `user_id` integer.
- Behavior: hard delete (`DELETE FROM users`). No soft-delete column.
- Response 204: no content.
- Errors:
  - `403` (`ForbiddenError`): a user cannot delete their own account (self-delete guard).
  - `404` (`UserNotFoundError`): target user not found in the caller's tenant.

## Users — business rules

1. Email is unique per tenant only; the same email may exist in different tenants.
2. `tenant_id` for created users is taken from the caller's verified claims, never from input.
3. Passwords are numeric PINs (6–14 digits), bcrypt-hashed before storage; plaintext is never stored or logged.
4. `password_hash` is never included in any response body (`UserData.to_response()` omits it).
5. PATCH applies only the fields present in the request body.
6. On email change, per-tenant uniqueness is re-checked before the update.
7. A user cannot delete their own account.
8. All reads, updates, and deletes are scoped to the caller's `tenant_id`; a user in another tenant is never visible or mutable.

## Error codes

| Code / class | HTTP | Condition |
|---|---|---|
| `UserNotFoundError` | 404 | Target user does not exist in the caller's tenant. |
| `UserAlreadyExistsError` | 409 | Email already used within the tenant (create, or update to a taken email). |
| `ForbiddenError` | 403 | Self-delete attempt. |
| `InvalidCredentialsError` | 401 | Login with wrong email/password. |
| `InvalidTokenError` | 401 | Refresh with an invalid/expired refresh token. |
| `V001` | 422 | Request body/query validation failure. |
