from __future__ import annotations

import logging

from app.data.auth_user import AuthUser
from app.services.abstract_service import AbstractService

logger = logging.getLogger(__name__)


class UserLookupService(AbstractService):
    """Real auth-side user lookup backed by ``UserStorage`` (replaces the
    ``NotImplementedUserLookupService`` stub).

    Returns an ``AuthUser`` projection (plan Q1: the auth identity is kept
    separate from the general ``UserData`` management entity). ``db_name`` is
    accepted for signature compatibility with the ``AuthService.login`` call
    site; the bound session already targets the tenant DB, so email is
    unambiguous within it (plan Q8 — full email->tenant routing is a follow-up).
    """

    async def get_by_email(self, email: str, db_name: str) -> AuthUser | None:
        user = await self.UserStorage.get_by_email(email)
        if user is None:
            return None
        return AuthUser(
            id=str(user.id),
            tenant_id=str(user.tenant_id),
            email=str(user.email),
            role=str(user.role),
            password_hash=str(user.password_hash),
        )
