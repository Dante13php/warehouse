from __future__ import annotations

from typing import Protocol

from app.data.auth_user import AuthUser
from app.services.abstract_service import AbstractService


class UserLookup(Protocol):
    async def get_by_email(self, email: str, db_name: str) -> AuthUser | None:
        ...


class NotImplementedUserLookupService(AbstractService):
    async def get_by_email(self, email: str, db_name: str) -> AuthUser | None:
        raise NotImplementedError(
            "UserLookup is not yet implemented. "
            "Wire a real UserStorage when the users table is available."
        )
