from __future__ import annotations

import logging

from fastapi import HTTPException

from app.data.auth_user import AuthUser
from app.storages.abstract_storage import AbstractStorage

logger = logging.getLogger(__name__)


class UserStorage(AbstractStorage):
    """Loads the full user record for the request's verified identity.

    ``CurrentUserMapper`` calls :meth:`get_by_id` lazily on first access to the
    full user profile, mirroring the CloudSale ``ActiveUserMapper`` concept where
    the mapper holds the DB-loaded user object (not just token claims). Identity
    (``user_id`` / ``tenant_id`` / ``role``) is established by the auth middleware
    from verified JWT/API-key credentials; this storage hydrates the remaining
    profile fields on demand.

    NOT-IMPLEMENTED STUB: there is no ``users`` table yet (the same constraint
    that leaves ``NotImplementedUserLookupService`` a stub). Rather than returning
    ``None`` (which the mapper would read as "user vanished"), this raises a
    ``404 Not Found`` to make it explicit that full-profile loading is not yet
    implemented. Wire a real ``tenant_id``-scoped lookup once the ``users`` table
    exists, and at that point return ``AuthUser | None`` instead of raising.
    """

    async def get_by_id(self, user_id: str) -> AuthUser | None:
        # No users table yet. Raise 404 to signal the lookup is unimplemented
        # rather than conflating it with a genuine "user not found" result.
        logger.debug("UserStorage stub invoked; no users table yet, raising 404.")
        raise HTTPException(
            status_code=404,
            detail="User profile loading is not implemented yet (no users table).",
        )
