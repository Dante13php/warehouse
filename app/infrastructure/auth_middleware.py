from __future__ import annotations

import logging

from typing import Any

from fastapi import HTTPException
from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.data.token import TokenData
from app.helpers.jwt import decode_access_token
from app.infrastructure.ioc import Ioc
from app.infrastructure.redis import get_redis_pool
from app.infrastructure.settings import Settings, get_settings
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_BEARER_PREFIX = "Bearer "

# Lowercased substring tokens that mark a User-Agent as a browser. "mozilla"
# alone covers every mainstream browser (all send a ``Mozilla/5.0`` prefix); the
# rest are defensive. This is the single, named knob for the channel rule — keep
# the discrimination logic isolated here so it is easy to read and tune later.
_BROWSER_UA_SIGNATURES: tuple[str, ...] = (
    "mozilla",
    "chrome",
    "safari",
    "firefox",
    "edg",
    "opera",
    "webkit",
    "gecko",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Establishes request identity *before* any controller runs.

    This is the single place authentication happens. It mirrors the CloudSale
    ``BaseController`` "initialize the active user if not initialized" concept,
    relocated to middleware so controllers stay free of auth logic and only read
    identity through ``ActiveUserMapper``.

    **Hard channel split by ``User-Agent``** — the two credential strategies are
    *mutually exclusive*. The channel is chosen up front from the ``User-Agent``
    header and the non-selected credential type is **never consulted** (not read,
    not decoded, not an error). There is no precedence and no fallback between
    channels.

    1. **Browser channel → JWT bearer only** (UI / refresh-token sessions). A
       request whose ``User-Agent`` contains a browser signature uses the JWT
       strategy exclusively. A valid ``Authorization: Bearer <jwt>`` yields a
       :class:`TokenData` attached to ``request.state.token_data``. A *malformed,
       expired, or absent* JWT is treated as anonymous — routes that require auth
       still enforce 401 via their own ``get_current_user`` dependency. Any
       API-key header on a browser request is ignored.
    2. **Machine channel → API key only** (external API clients; e.g. curl,
       Insomnia). A request whose ``User-Agent`` is non-browser, or is
       missing/empty, uses the API-key strategy exclusively. When the configured
       API-key header is **absent**, the request is anonymous (a route may be
       public; a missing credential is not an error). When the header is
       **present**, it is resolved to a user via ``ApiKeyStorage``: on success the
       resolved user seeds a :class:`TokenData`; if the key cannot be resolved
       (``None``), the middleware returns **401 immediately** — a presented
       credential that fails must never silently downgrade to anonymous access.
       While the ``api_keys`` table does not yet exist, ``ApiKeyStorage`` raises
       an ``HTTPException(404)`` to signal the feature is unimplemented; the
       middleware surfaces that status verbatim (it must catch it, since an
       exception raised inside ``BaseHTTPMiddleware`` would otherwise become a
       500). Any ``Authorization`` bearer on a machine request is ignored.

    The ``User-Agent`` selects *which channel runs* only; it never grants
    identity by itself. Both channels still require a valid credential, and
    ``tenant_id`` / ``role`` always come from verified JWT claims or the API-key
    lookup result — never from the request body, query params, or ``User-Agent``.
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        # One pool-backed client shared across all requests. Connections are
        # borrowed from the pool per command and returned automatically —
        # no per-request create/aclose needed.
        self._redis = Redis(connection_pool=get_redis_pool())

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = get_settings()
        request.state.token_data = None

        if self._is_browser_request(request):
            # Browser channel: JWT only. The API-key header is never consulted.
            token_data = self._authenticate_jwt(request, settings)
        else:
            # Machine channel: API key only. The Authorization bearer is never
            # consulted.
            api_key = request.headers.get(settings.api_key_header)
            if api_key is None:
                # No credential presented on a possibly-public route: anonymous.
                token_data = None
            else:
                try:
                    token_data = await self._authenticate_api_key(api_key, settings)
                except HTTPException as exc:
                    # The storage signalled an HTTP condition (e.g. the
                    # not-implemented 404 stub). Surface it as a proper response;
                    # letting it propagate from BaseHTTPMiddleware would yield 500.
                    return self._http_error(exc)
                if token_data is None:
                    # A credential was explicitly presented and failed to
                    # resolve: deny rather than downgrade to anonymous.
                    return self._unauthorized("Invalid API key")

        request.state.token_data = token_data
        return await call_next(request)

    def _is_browser_request(self, request: Request) -> bool:
        """Return ``True`` when the ``User-Agent`` looks like a browser.

        A missing or empty ``User-Agent`` is **not** a browser: browsers always
        send one, while scripted clients sometimes omit it, so "no UA" belongs to
        the machine channel. The decision is a substring check against
        :data:`_BROWSER_UA_SIGNATURES` and is the only place the channel rule
        lives.
        """
        user_agent = request.headers.get("User-Agent")
        if not user_agent:
            return False
        user_agent = user_agent.lower()
        return any(signature in user_agent for signature in _BROWSER_UA_SIGNATURES)

    def _authenticate_jwt(
        self, request: Request, settings: Settings
    ) -> TokenData | None:
        header = request.headers.get("Authorization")
        if header is None or not header.startswith(_BEARER_PREFIX):
            return None
        token = header[len(_BEARER_PREFIX):].strip()
        if not token:
            return None
        try:
            return decode_access_token(token, settings)
        except JWTError:
            # Malformed/expired bearer on a possibly-public route: anonymous.
            # Protected routes still 401 via get_current_user.
            logger.debug("Invalid JWT bearer presented; treating request as anonymous.")
            return None

    async def _authenticate_api_key(
        self, api_key: str, settings: Settings
    ) -> TokenData | None:
        ioc = Ioc(session=None, token_data=None, redis=self._redis, settings=settings)
        user = await ioc.ApiKeyStorage.get_user_by_api_key(api_key)
        if user is None:
            return None
        return TokenData(sub=user.id, tenant_id=user.tenant_id, role=user.role)

    @staticmethod
    def _unauthorized(message: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": {"code": "A401", "message": message}},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @staticmethod
    def _http_error(exc: HTTPException) -> JSONResponse:
        # Translate an HTTPException raised by a storage/strategy into a response.
        # BaseHTTPMiddleware does not route exceptions through the app's
        # ExceptionMiddleware, so an uncaught HTTPException here becomes a 500.
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": f"A{exc.status_code}", "message": exc.detail}},
            headers=exc.headers or None,
        )
