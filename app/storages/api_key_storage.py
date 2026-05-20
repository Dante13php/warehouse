from __future__ import annotations

import logging

from fastapi import HTTPException

from app.data.auth_user import AuthUser
from app.storages.abstract_storage import AbstractStorage

logger = logging.getLogger(__name__)


class ApiKeyStorage(AbstractStorage):
    # NOT-IMPLEMENTED STUB: no api_keys table exists yet. It raises 404 rather
    # than returning None so the stub is not confused with a genuine "key not
    # found" (which is the 401 the middleware will raise once a real lookup
    # exists). Once the api_keys table exists, wire a hashed-key, tenant_id-scoped
    # lookup and return AuthUser | None instead of raising.

    async def get_user_by_api_key(self, api_key: str) -> AuthUser | None:
        logger.debug("ApiKeyStorage stub invoked; no api_keys table yet, raising 404.")
        raise HTTPException(
            status_code=404,
            detail="API-key authentication is not implemented yet (no api_keys table).",
        )

    async def get_api_key_by_user_id(self, user_id: str) -> str | None:
        logger.debug("ApiKeyStorage stub invoked; no api_keys table yet, raising 404.")
        raise HTTPException(
            status_code=404,
            detail="API-key lookup is not implemented yet (no api_keys table).",
        )
