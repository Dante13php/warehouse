# Auth Channel Split by User-Agent (hard JWT vs API-key separation)

## Status

`implemented`

## Source task / spec

Today `AuthMiddleware` (`app/infrastructure/auth_middleware.py`) authenticates with a
**precedence** model: it tries the JWT bearer strategy first and only falls back to the
API-key strategy when no valid JWT is present. Both credentials may be presented on the
same request; JWT simply wins.

The user wants a **hard channel split** instead of precedence. The discriminator is the
**`User-Agent` request header**:

- **Browser request** (User-Agent contains a browser signature) → use the **JWT** strategy
  only. Any presented API key is **ignored** (not consulted, not an error).
- **Non-browser / machine-to-machine request** (User-Agent does not look like a browser,
  e.g. Insomnia, curl, an external client) → use the **API-key** strategy only. Any
  presented JWT bearer is **ignored** (not consulted, not an error).

Clarifications captured from the user:

- **Q1 → (b)**: hard separation of the two channels — never both, never fallback between
  them. The channel is chosen up front; the other credential type is ignored for that
  request.
- **Q2**: the discriminator is the **User-Agent header**. A browser signature in
  User-Agent ⇒ browser channel; anything else ⇒ machine channel.
- **Q3**: `ApiKeyStorage` stays a **stub** (raises 404 "not implemented"); the real
  DB-backed lookup is deferred. **No database agent** is involved in this task.

## Current state (verified by reading the code)

- `app/infrastructure/auth_middleware.py` — `AuthMiddleware(BaseHTTPMiddleware)`.
  `dispatch` calls `_authenticate_jwt` first; if that returns `None`, and the configured
  API-key header is present, it calls `_authenticate_api_key` and (a) returns 401 if the
  key cannot be resolved, or (b) catches the stub's `HTTPException(404)` and surfaces it.
  This is the **precedence** behavior to be replaced.
- `_authenticate_jwt(request, settings)` — reads `Authorization: Bearer <jwt>`, decodes via
  `decode_access_token`; malformed/expired ⇒ `None` (anonymous).
- `_authenticate_api_key(api_key, settings)` — builds a request-scoped `Ioc` (no session),
  calls `ApiKeyStorage.get_user_by_api_key`, returns `TokenData` from the resolved user.
- `app/storages/api_key_storage.py` — `ApiKeyStorage` stub; `get_user_by_api_key` raises
  `HTTPException(404, "API-key authentication is not implemented yet...")`. **Unchanged by
  this task.**
- `app/infrastructure/settings.py` — has `api_key_header: str = "X-API-Key"`. No User-Agent
  related setting yet.
- `app/data/token.py` — `TokenData(sub, tenant_id, role)`.
- The downstream contract is unchanged: middleware sets `request.state.token_data`
  (a `TokenData` or `None`); `get_ioc` reads it; `ActiveUserMapper` is the single read
  surface. **None of that changes** — only *which strategy runs* changes.

## Scope

Replace the JWT-precedence-then-API-key logic in `AuthMiddleware.dispatch` with a
**User-Agent-driven channel selector**. Exactly one strategy runs per request.

### 1. Channel detection helper — `app/infrastructure/auth_middleware.py`

Add a small, clearly-named, maintainable classifier that decides the channel from the
`User-Agent` header. Proposed shape:

- A module-level constant tuple of browser signature tokens (lowercased), e.g.
  `("mozilla", "chrome", "safari", "firefox", "edg", "opera", "webkit", "gecko")`.
  `"mozilla"` alone covers the overwhelming majority of real browsers (every mainstream
  browser sends a `Mozilla/5.0` prefix), the rest are defensive.
- A method `_is_browser_request(request) -> bool` that reads `User-Agent`, lowercases it,
  and returns `True` if any signature token is a substring. A **missing or empty**
  User-Agent ⇒ **not a browser** ⇒ machine channel (browsers always send a User-Agent;
  scripted clients sometimes omit it, so "no UA" belongs to the machine channel).
- Keep the discrimination logic isolated in this one method with the signature list as a
  named constant, so the rule is easy to read and adjust later (maintainability
  requirement).

### 2. Channel-split dispatch — `app/infrastructure/auth_middleware.py`

Rewrite `dispatch` to:

1. Set `request.state.token_data = None`.
2. If `_is_browser_request(request)` is `True` → **JWT channel**:
   - `token_data = self._authenticate_jwt(request, settings)`.
   - Do **not** read or consult the API-key header at all.
   - Malformed/expired/absent JWT ⇒ `token_data` stays `None` (anonymous) — unchanged
     semantics; protected routes still enforce 401 via `get_current_user`.
3. Else → **API-key channel**:
   - Read the configured API-key header. If **absent** ⇒ anonymous (`token_data = None`),
     consistent with "a route may be public; missing credentials are not an error here".
   - If **present** ⇒ call `_authenticate_api_key`, preserving the existing two behaviors:
     - resolved user ⇒ `TokenData`;
     - unresolved (`None`) ⇒ **401 immediately** (a presented credential that fails must
       not downgrade to anonymous);
     - stub `HTTPException(404)` ⇒ caught and surfaced via `_http_error` (an exception
       raised inside `BaseHTTPMiddleware` would otherwise become a 500).
   - Do **not** read or consult the `Authorization` bearer header at all.
4. `request.state.token_data = token_data`; `return await call_next(request)`.

The existing helper methods (`_authenticate_jwt`, `_authenticate_api_key`,
`_unauthorized`, `_http_error`) are **reused as-is**; only `dispatch` is restructured and
the new `_is_browser_request` is added.

### 3. Docstring + comments

Update the `AuthMiddleware` class docstring to describe the **channel split by User-Agent**
(replacing the "precedence, JWT wins" description). State explicitly that the two channels
are mutually exclusive and that the non-selected credential type is ignored.

### 4. Documentation (docs-writer scope)

- `.claude/rules/RULES.md` — the **Authentication** subsection currently says: *"two
  strategies, tried in precedence order: JWT bearer first ... then API key ... JWT wins
  when both are present."* Replace that with the User-Agent channel-split description
  (browser ⇒ JWT only; non-browser ⇒ API key only; the other credential is ignored;
  missing/empty User-Agent ⇒ machine channel).
- `docs/architecture/IOC.md` — update only if it restates the precedence model (verify and
  adjust the auth-middleware reference if present).
- `docs/application-stack/auth.md` (if present) — update the middleware flow description to
  the channel split.
- `CLAUDE.md` — the Infrastructure/auth note is high-level; update only if a sentence
  becomes inaccurate.
- This plan's status → `implemented` at the end.

## Out of scope

- The `users` / `api_keys` tables, migrations, seed SQL — deferred; `ApiKeyStorage` stays a
  404 stub. **No database agent.**
- Any change to `ApiKeyStorage`, `UserStorage`, `ActiveUserMapper`, `get_ioc`, `TokenData`,
  or the login/refresh/logout flow. The middleware's *output contract*
  (`request.state.token_data`) is unchanged.
- Making the User-Agent signature list configurable via settings — kept as a named
  in-module constant for now (can be promoted to settings later if needed).
- A "force channel" override header or query param — out of scope; the channel is decided
  solely by User-Agent.
- Frontend / UI work.
- Rate limiting, API-key issuance/rotation, hashing scheme.

## Acceptance criteria

- A request whose `User-Agent` contains a browser signature (e.g. `Mozilla/5.0 ...`):
  - with a valid `Authorization: Bearer <jwt>` ⇒ `request.state.token_data` is the decoded
    `TokenData`; `ActiveUserMapper.is_initialized()` is `True`.
  - with **only** an API-key header (no/invalid JWT) ⇒ the API-key header is **ignored**;
    `request.state.token_data` is `None` (anonymous); **no 401, no 404** from the API-key
    path (it is never consulted).
  - with a malformed/expired JWT ⇒ anonymous (no 500); protected routes still 401 via
    `get_current_user`.
- A request whose `User-Agent` is non-browser (e.g. `insomnia/2024`, `curl/8.0`) or
  missing/empty:
  - with the configured API-key header present ⇒ `_authenticate_api_key` runs; with the
    current stub this surfaces **404** (not-implemented); a presented-but-unresolvable key
    (once a real lookup exists) ⇒ **401**.
  - with **only** a JWT bearer (no API-key header) ⇒ the bearer is **ignored**;
    `request.state.token_data` is `None` (anonymous); the JWT is never decoded for identity.
  - with no credentials at all ⇒ anonymous; public routes still succeed.
- Exactly **one** strategy is invoked per request; the non-selected credential type is never
  consulted (verifiable by reading `dispatch`: only one of `_authenticate_jwt` /
  `_authenticate_api_key` is reachable per branch).
- The channel decision lives in a single, named method (`_is_browser_request`) backed by a
  named signature constant — easy to read and adjust.
- `tenant_id` / `role` still come only from verified JWT claims or the API-key lookup
  result — never from request body/query/User-Agent.
- `python -c "import app.main"` imports cleanly.
- Docs in `.claude/rules/RULES.md` (and any other file that restated precedence) accurately
  describe the User-Agent channel split.

## Impacted files or modules

| File | Action | Owner |
|---|---|---|
| `app/infrastructure/auth_middleware.py` | updated (add `_is_browser_request`; rewrite `dispatch` to channel-split; update docstring) | implementer |
| `.claude/rules/RULES.md` | updated (Authentication subsection: precedence → channel split) | docs-writer |
| `docs/architecture/IOC.md` | updated only if it restates precedence | docs-writer |
| `docs/application-stack/auth.md` | updated if present | docs-writer |
| `CLAUDE.md` | updated only if a sentence becomes inaccurate | docs-writer |
| `docs/plans/2026-05-20-auth-channel-split-user-agent.md` | status → implemented at end | docs-writer |

## Risks

- **User-Agent is spoofable.** A machine client can send a browser User-Agent to force the
  JWT channel, or a browser-based attacker could (via a non-browser context) force the
  API-key channel. This is acceptable per the user's explicit design: User-Agent is the
  chosen discriminator. **Security implication:** this makes User-Agent a (weak) trust input
  for *channel selection only* — it never grants identity by itself; both channels still
  require a valid credential. Called out for the security agent to confirm the threat model
  is acceptable and that no privilege is gained merely by picking a channel.
- **Edge User-Agents.** Some legitimate non-browser tools embed "Mozilla" (e.g. certain
  HTTP libraries, link previewers); they would be routed to the JWT channel. Acceptable for
  now; the signature list is a single named constant that can be tuned.
- **Behavior change vs. existing tests.** The prior precedence behavior (JWT tried first
  regardless of UA) changes. Any test that presented an API key with a browser-ish (or
  default `testclient`) User-Agent and expected the API-key 404/401 will now see anonymous,
  and vice-versa. Note: Starlette `TestClient` sends `User-Agent: testclient` by default,
  which is **non-browser** ⇒ machine channel; tests must set an explicit browser User-Agent
  to exercise the JWT channel. Reviewer/implementer must update or add tests accordingly.
- **No live Redis/DB in CI.** Verification limited to TestClient + unit-level behavior.

## Agent decisions

- planner: this plan (no code written).
- ui-designer: **not required** (no UI scope).
- database: **not required** — no schema/migration; `ApiKeyStorage` stays a stub (per Q3).
- implementer: owns `app/infrastructure/auth_middleware.py` to this contract.
- reviewer: verify exactly one strategy runs per channel, the non-selected credential is
  never consulted, missing/empty User-Agent ⇒ machine channel, anonymous-fallback semantics
  preserved, 401/404 behaviors preserved on the API-key channel, type hints, no `print`,
  no credential logging.
- security: **required** (auth, trust boundary, credential channel selection). Run after
  reviewer. Focus: User-Agent as channel discriminator never grants identity by itself;
  malformed credentials never partially initialize identity; no credential/UA logging that
  leaks secrets; tenant_id/role still only from verified claims or API-key lookup.
- docs-writer: owns the doc/MD updates and sets this plan to `implemented`.
- spec-writer: **skip** — infrastructural change, no new user-facing endpoint.
- version-control: commit plan + code + docs together at the end.

## Approval log

- 2026-05-20: plan drafted from the user's answered clarifying questions (Q1 hard split,
  Q2 User-Agent discriminator, Q3 API-key storage stays a stub / no database agent).
  Awaiting user approval before implementation starts.
- 2026-05-20: user approved. Implemented `_is_browser_request` + `_BROWSER_UA_SIGNATURES`
  constant and channel-split `dispatch` in `app/infrastructure/auth_middleware.py`; class
  docstring updated to the channel split. Docs updated: `.claude/rules/RULES.md`,
  `docs/architecture/IOC.md`, `docs/application-stack/auth.md`. `CLAUDE.md` needed no change
  (no auth-mechanism sentence). Reviewer and security (mandatory) passed with no findings;
  threat model accepted (User-Agent selects channel only, never grants identity).
  `python -c "import app.main"` imports cleanly. Status set to `implemented`.
