# Authentication

Warehouse uses **stateless JWT access tokens** for request authentication and
**revocable refresh tokens stored in Redis** for session continuity. Identity and
authorization travel inside the signed token, so most requests need no database or
cache lookup to authenticate. External API clients can authenticate with a
per-user **API key** instead of a JWT.

> Status: the Redis service that backs refresh tokens is **implemented** (Docker);
> the auth endpoints and refresh-token flow are **implemented**; the
> **auth middleware** (JWT + API-key identity initialization) is **implemented**.
> The `users` and `api_keys` tables are **planned** — until they exist the
> `UserStorage` and `ApiKeyStorage` lookups are **not-implemented stubs that
> raise `404 Not Found`**, making the missing feature explicit rather than
> masquerading as "not found". The API-key branch is fully wired but resolves no
> users yet.

## Building blocks

| Piece | Where | Purpose |
|---|---|---|
| Access token (JWT) | Sent by client on every request | Stateless proof of identity + role + tenant. Short-lived (15–60 min). |
| Refresh token | Stored in Redis, returned to client | Long-lived, **revocable**. Used to mint new access tokens. |
| API key | Sent by external clients in the `X-API-Key` header | Per-user credential for non-UI/API clients; resolved to a user by `ApiKeyStorage`. |
| `users` table | Per-tenant database | Tenant-scoped user records, bcrypt password hashes, role. |
| `api_keys` table | Per-tenant database (planned) | Maps a hashed API key to its owning user. |
| Auth middleware | Request boundary | `AuthMiddleware` (`app/infrastructure/auth_middleware.py`). Runs before every controller; establishes a trusted identity from the JWT bearer, then the API key. |
| `UserStorage` | Storage | Loads the full user record (`AuthUser`) by id for `CurrentUserMapper.load()`. Not-implemented stub (raises 404) until the `users` table exists. |
| `CurrentUserMapper` | Per-request mapper | The single read surface controllers use for identity. Claim-backed identity (`is_initialized()`, `user_id`, `tenant_id`, `role`, `is_admin()`, `is_manager()`) needs no DB; the **full user record** is lazy-loaded and memoized via `await load()` (then `user` / `email`), and `get_api_key()` lazy-loads the user's API key — mirroring CloudSale's `ActiveUserMapper`. |

## Token claims

The JWT carries exactly these claims:

| Claim | Meaning |
|---|---|
| `sub` | User id. |
| `tenant_id` | The tenant the user belongs to. Drives database routing. |
| `role` | `manager` or `staff`. |
| `exp` | Expiry timestamp (15–60 minutes out). |

`tenant_id` and `role` are read **only** from the verified token — never from the
request body or query params.

## Users and roles

- Users live in the tenant's own `client_{slug}` database, in a tenant-scoped
  `users` table (every row carries `tenant_id`).
- Two roles: **`manager`** and **`staff`**. Authorization checks key off the
  `role` claim.
- Passwords are hashed with **bcrypt**. Plaintext passwords are never stored or
  logged.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/auth/login` | Exchange credentials for an access token + refresh token. |
| `POST` | `/auth/refresh` | Exchange a valid refresh token for a new access token (and rotated refresh token). |
| `POST` | `/auth/logout` | Revoke the refresh token, ending the session. |

## Flows

### Login

```
client                        FastAPI                     Redis / DB
  │   POST /auth/login            │                            │
  │   { email, password }         │                            │
  │ ─────────────────────────────▶│                            │
  │                               │  load user (tenant DB)     │
  │                               │ ──────────────────────────▶│
  │                               │  verify bcrypt hash        │
  │                               │  mint access JWT           │
  │                               │  store refresh token       │
  │                               │ ──────────────────────────▶│  (Redis)
  │   { access, refresh }         │                            │
  │ ◀─────────────────────────────│                            │
```

1. The client posts credentials.
2. The service loads the user from the tenant database and verifies the password
   against the bcrypt hash.
3. On success it mints a short-lived access JWT (`sub`, `tenant_id`, `role`,
   `exp`) and creates a refresh token.
4. The refresh token is stored in Redis (keyed so it can be revoked), and both
   tokens are returned.

### Authenticated request

```
client ── Authorization: Bearer <access JWT>  ──▶ AuthMiddleware
      └── X-API-Key: <api key>  (alternative) ──▶   │ 1. try JWT bearer (decode + verify)
                                                     │ 2. else, if API key present, resolve via ApiKeyStorage
                                                     │ attach request.state.token_data
                                                     ▼
                                          identity{ sub, tenant_id, role }
                                                     │  get_ioc reads request.state.token_data
                                                     ▼
                                  controller → self.CurrentUserMapper → …
```

`AuthMiddleware` runs before any controller and establishes identity once per
request, attaching a verified `TokenData` to `request.state.token_data`. It tries
two strategies in precedence order:

1. **JWT bearer** — decode and verify the `Authorization: Bearer <jwt>` token. No
   Redis or DB lookup is needed for a valid, unexpired access token; that is the
   point of stateless JWTs. A malformed or expired bearer is treated as anonymous
   here (routes that require auth still return 401 via `get_current_user`).
2. **API key** — only attempted when no valid JWT is present. The configured
   `X-API-Key` header is resolved to a user via `ApiKeyStorage`, and the resolved
   user seeds the identity. If the header is **present but the key cannot be
   resolved** (`None`), the middleware returns **401 immediately** — presenting a
   credential that fails never downgrades to anonymous access. While the
   `api_keys` table does not yet exist, `ApiKeyStorage` raises `404 Not Found` to
   signal the feature is unimplemented; the middleware catches that and surfaces
   the 404 (an exception left to propagate from `BaseHTTPMiddleware` would
   otherwise become a 500).

`get_ioc` then reads `request.state.token_data` (it never decodes a token itself),
and controllers read identity only through `self.CurrentUserMapper`. Controllers
never parse the raw token or API key themselves.

### Refresh

```
client                        FastAPI                        Redis
  │  POST /auth/refresh           │                             │
  │  { refresh }                  │                             │
  │ ─────────────────────────────▶│                             │
  │                               │  look up refresh token      │
  │                               │ ───────────────────────────▶│
  │                               │  (valid & not revoked?)     │
  │                               │  rotate: revoke old,        │
  │                               │  store new refresh          │
  │                               │ ───────────────────────────▶│
  │                               │  mint new access JWT        │
  │  { access, refresh }          │                             │
  │ ◀─────────────────────────────│                             │
```

1. The client posts its refresh token.
2. The service checks Redis to confirm the token exists and has not been revoked.
3. It rotates the refresh token (revoke the old, store a new one) and mints a
   fresh access JWT.
4. Both new tokens are returned.

Rotation means a stolen refresh token has a limited window and is invalidated as
soon as the legitimate client refreshes.

### Logout

```
client ── POST /auth/logout { refresh } ──▶ FastAPI ──▶ delete refresh key (Redis)
```

Logout deletes (revokes) the refresh token in Redis. The access token remains
technically valid until it expires, but with a 15–60 minute lifetime its exposure
window is small, and the session cannot be renewed once the refresh token is gone.

## Why this design

- **Stateless access tokens** keep the hot path fast: routine requests
  authenticate from the signed token alone, with no shared session store to hit.
- **Redis-backed refresh tokens** restore revocability — the one thing pure
  stateless JWTs lack — so logout and rotation actually invalidate sessions.
- **Short access-token lifetimes** bound the damage of a leaked access token.
- **Claims carry tenant and role**, which lets the database router and
  authorization checks work without extra lookups, while keeping `tenant_id` and
  `role` out of attacker-controllable request fields.

## Security rules recap

- JWTs are stateless and short-lived (15–60 minutes).
- Refresh tokens live in Redis and are revocable.
- Claims carry `sub`, `tenant_id`, `role`, `exp`.
- Identity is established in `AuthMiddleware` before any controller; controllers
  read it only through `CurrentUserMapper`. `get_ioc` reads `request.state`, never
  decoding a token itself.
- JWT takes precedence over the API key. A malformed JWT is anonymous; a presented
  API key that fails to resolve is rejected with 401 (never anonymous).
- Never trust `tenant_id` or `role` from the request body or query params — always
  read them from the verified token (or the API-key lookup result).
- Credentials (JWTs, API keys) are never logged.
- Passwords are bcrypt-hashed; never logged.
