from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from app.controllers.db_base_controller import DbBaseController
from app.helpers.security import require_authentication
from app.requests.users.create_user_request import CreateUserRequest
from app.requests.users.update_user_request import UpdateUserRequest

logger = logging.getLogger(__name__)

# Every route requires authentication (plan Q7: no role gate this task). The
# gate reads middleware-established identity and 401s when anonymous.
router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_authentication)],
)


class UsersController(DbBaseController):
    # Flat-flow controller: no try/except. Domain errors raised by UserService
    # (ApplicationError subclasses) bubble to the global handler in app/main.py.
    # No business logic, no direct DB access here. Identity is read only through
    # ActiveUserMapper (in the service); the controller shapes responses via
    # UserData.to_response() so password_hash is never returned.

    async def list_users(self) -> list[dict[str, Any]]:
        users = await self.UserService.list_users()
        return [user.to_response() for user in users]

    async def get_user(self, user_id: int) -> dict[str, Any]:
        user = await self.UserService.get_user(user_id)
        return user.to_response()

    async def create_user(self, body: CreateUserRequest) -> dict[str, Any]:
        user = await self.transaction.wrap(
            self.session,
            self.UserService.create_user,
            email=body.email,
            password=body.password,
            role=body.role,
        )
        return user.to_response()

    async def update_user(
        self, user_id: int, body: UpdateUserRequest
    ) -> dict[str, Any]:
        fields = body.model_dump(exclude_unset=True)
        user = await self.transaction.wrap(
            self.session,
            self.UserService.update_user,
            user_id,
            fields,
        )
        return user.to_response()

    async def delete_user(self, user_id: int) -> Response:
        await self.transaction.wrap(
            self.session,
            self.UserService.delete_user,
            user_id,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("")
async def list_users(
    ctrl: UsersController = Depends(UsersController),
) -> list[dict[str, Any]]:
    return await ctrl.list_users()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    ctrl: UsersController = Depends(UsersController),
) -> dict[str, Any]:
    return await ctrl.create_user(body)


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    ctrl: UsersController = Depends(UsersController),
) -> dict[str, Any]:
    return await ctrl.get_user(user_id)


@router.patch("/{user_id}")
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    ctrl: UsersController = Depends(UsersController),
) -> dict[str, Any]:
    return await ctrl.update_user(user_id, body)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    ctrl: UsersController = Depends(UsersController),
) -> Response:
    return await ctrl.delete_user(user_id)
