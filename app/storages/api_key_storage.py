from __future__ import annotations

import logging

from fastapi import HTTPException

from app.data.auth_user import AuthUser
from app.storages.abstract_storage import AbstractStorage

logger = logging.getLogger(__name__)


class ApiKeyStorage(AbstractStorage):
    """Resolves an external-client API key to its owning user.

    This is the API-key counterpart to the JWT bearer path. The middleware calls
    :meth:`get_user_by_api_key` when a request presents the configured API-key
    header; a resolved :class:`AuthUser` would seed the request identity.

    NOT-IMPLEMENTED STUB: there is no ``api_keys`` table yet (the same constraint
    that leaves ``NotImplementedUserLookupService`` a stub). Rather than silently
    returning ``None`` (which would masquerade as "key not found"), this raises a
    ``404 Not Found`` to make it explicit that the API-key feature is not yet
    implemented — distinct from a genuine "key not found" (which is a ``401`` the
    middleware raises once a real lookup exists). Wire a real lookup
    (hashed-key comparison, ``tenant_id`` scoping) once the ``api_keys`` table
    exists, and at that point return ``AuthUser | None`` instead of raising.
    """

    async def get_user_by_api_key(self, api_key: str) -> AuthUser | None:
        # No api_keys table yet. Raise 404 to signal the feature is unimplemented
        # rather than conflating it with a "key not found" (401) result. The
        # middleware translates this into a 404 response (it cannot let an
        # exception propagate as a 500 from within BaseHTTPMiddleware).
        logger.debug("ApiKeyStorage stub invoked; no api_keys table yet, raising 404.")
        raise HTTPException(
            status_code=404,
            detail="API-key authentication is not implemented yet (no api_keys table).",
        )

    async def get_api_key_by_user_id(self, user_id: str) -> str | None:
        # Reverse lookup used by CurrentUserMapper.get_api_key() (mirrors the
        # CloudSale ActiveUserMapper lazy API-key load). Unimplemented until the
        # api_keys table exists; raise 404 to make that explicit.
        logger.debug("ApiKeyStorage stub invoked; no api_keys table yet, raising 404.")
        raise HTTPException(
            status_code=404,
            detail="API-key lookup is not implemented yet (no api_keys table).",
        )
