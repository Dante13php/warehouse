from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from app.data.auth_user import AuthUser

if TYPE_CHECKING:
    from app.infrastructure.ioc import Ioc


class UserLookup(Protocol):
    async def get_by_email(self, email: str, db_name: str) -> AuthUser | None:
        ...


class NotImplementedUserLookupService:
    def __init__(self, ioc: Ioc) -> None:
        self._ioc = ioc

    async def get_by_email(self, email: str, db_name: str) -> AuthUser | None:
        raise NotImplementedError(
            "UserLookup is not yet implemented. "
            "Wire a real UserStorage when the users table is available."
        )
