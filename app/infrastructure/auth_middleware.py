from __future__ import annotations

import logging

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


class AuthMiddleware(BaseHTTPMiddleware):
    """Establishes request identity *before* any controller runs.

    This is the single place authentication happens. It mirrors the CloudSale
    ``BaseController`` "initialize the active user if not initialized" concept,
    relocated to middleware so controllers stay free of auth logic and only read
    identity through ``CurrentUserMapper``.

    Two pluggable strategies, tried in precedence order:

    1. **JWT bearer** (UI / refresh-token sessions). A valid
       ``Authorization: Bearer <jwt>`` yields a :class:`TokenData` attached to
       ``request.state.token_data``. A *malformed or expired* JWT is treated as
       anonymous here — routes that require auth still enforce 401 via their own
       ``get_current_user`` dependency. JWT takes precedence: the API-key branch
       is only attempted when no valid JWT is present.
    2. **API key** (external API clients). When the configured API-key header is
       present, it is resolved to a user via ``ApiKeyStorage``. On success the
       resolved user seeds a :class:`TokenData`. If the header is present but the
       key cannot be resolved (``None``), the middleware returns **401
       immediately** — a presented credential that fails must never silently
       downgrade to anonymous access. While the ``api_keys`` table does not yet
       exist, ``ApiKeyStorage`` raises an ``HTTPException(404)`` to signal the
       feature is unimplemented; the middleware surfaces that status verbatim
       (it must catch it, since an exception raised inside ``BaseHTTPMiddleware``
       would otherwise become a 500).

    If neither strategy yields identity (and no API key was presented),
    ``request.state.token_data`` is left ``None`` (anonymous); public routes
    still work.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = get_settings()
        request.state.token_data = None

        token_data = self._authenticate_jwt(request, settings)

        if token_data is None:
            api_key = request.headers.get(settings.api_key_header)
            if api_key is not None:
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
        redis = Redis(connection_pool=get_redis_pool())
        try:
            ioc = Ioc(session=None, token_data=None, redis=redis, settings=settings)
            user = await ioc.ApiKeyStorage.get_user_by_api_key(api_key)
        finally:
            await redis.aclose()
        if user is None:
            return None
        # Identity is sourced from the resolved user record, never from the
        # request body or query params.
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
