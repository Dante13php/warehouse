from __future__ import annotations

import logging
from typing import Any

from app.data.data_collection import DataCollection
from app.data.user_data import UserData
from app.helpers.password import hash_password
from app.services.abstract_service import AbstractService

logger = logging.getLogger(__name__)


class UserService(AbstractService):
    """Users management business logic (flat-flow: no try/except, no
    transactions, no direct DB access).

    Access control: per plan Q7, role-based permission gates are OUT OF SCOPE
    for this task. The endpoints require authentication only (enforced at the
    route boundary); any authenticated user may call any method here. The one
    behavioral guard retained is the self-delete guard (Q12).

    Identity (``tenant_id``, ``user_id``) is read ONLY from ``ActiveUserMapper``
    (verified claims) — never from request input.
    """

    async def list_users(self) -> DataCollection[UserData]:
        return await self.UserStorage.list()

    async def get_user(self, user_id: int) -> UserData:
        user = await self.UserStorage.get_by_id(user_id)
        if user is None:
            raise self.UserNotFoundError.get()
        return user

    async def create_user(
        self, email: str, password: str, role: str
    ) -> UserData:
        existing = await self.UserStorage.get_by_email(email)
        if existing is not None:
            raise self.UserAlreadyExistsError.get()

        user = UserData(
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        return await self.UserStorage.create(user)

    async def update_user(self, user_id: int, fields: dict[str, Any]) -> UserData:
        user = await self.UserStorage.get_by_id(user_id)
        if user is None:
            raise self.UserNotFoundError.get()

        if "email" in fields:
            new_email = fields["email"]
            if new_email != user.email:
                clash = await self.UserStorage.get_by_email(new_email)
                if clash is not None and clash.id != user.id:
                    raise self.UserAlreadyExistsError.get()
            user.email = new_email

        if "password" in fields:
            user.password_hash = hash_password(fields["password"])

        if "role" in fields:
            user.role = fields["role"]

        updated = await self.UserStorage.update(user)
        if updated is None:
            # Row vanished between read and write (concurrent delete).
            raise self.UserNotFoundError.get()
        return updated

    async def delete_user(self, user_id: int) -> None:
        # Self-delete guard (Q12): a user cannot delete their own account.
        active_user_id = int(self.ActiveUserMapper.user_id)
        if user_id == active_user_id:
            raise self.ForbiddenError.get("You cannot delete your own account")

        deleted = await self.UserStorage.delete(user_id)
        if not deleted:
            raise self.UserNotFoundError.get()
