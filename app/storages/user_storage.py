from __future__ import annotations

import logging

from fastapi import HTTPException

from app.data.auth_user import AuthUser
from app.storages.abstract_storage import AbstractStorage

logger = logging.getLogger(__name__)


class UserStorage(AbstractStorage):
    # NOT-IMPLEMENTED STUB: no users table exists yet. It raises 404 rather than
    # returning None so the mapper does not read the stub as "user vanished".
    # Once the users table exists, wire a tenant_id-scoped lookup and return
    # AuthUser | None instead of raising.

    async def get_by_id(self, user_id: str) -> AuthUser | None:
        logger.debug("UserStorage stub invoked; no users table yet, raising 404.")
        raise HTTPException(
            status_code=404,
            detail="User profile loading is not implemented yet (no users table).",
        )
