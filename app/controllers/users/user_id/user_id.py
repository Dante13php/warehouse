from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Response, status

from app.controllers.db_base_controller import DbBaseController
from app.helpers.security import require_authentication
from app.requests.users.update_user_request import UpdateUserRequest

logger = logging.getLogger(__name__)

# Single-resource routes only — those keyed by the {user_id} path parameter
# (GET/PATCH/DELETE /users/{user_id}), per the path-parameter-subfolder
# convention. Collection-level routes (GET /users, POST /users) live in the
# parent users.py. Same /users prefix and authentication gate as the collection
# router; both routers are registered in app/main.py.
router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_authentication)],
)


class UserIdController(DbBaseController):
    # Flat-flow controller: no try/except. Domain errors raised by UserService
    # (ApplicationError subclasses) bubble to the global handler in app/main.py.
    # No business logic, no direct DB access here. Identity is read only through
    # ActiveUserMapper (in the service); the controller shapes responses via
    # UserData.to_response() so password_hash is never returned.

    async def get(self, user_id: int) -> dict[str, Any]:
        user = await self.UserService.get_user(user_id)
        return user.to_response()

    async def update(
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

    async def delete(self, user_id: int) -> Response:
        await self.transaction.wrap(
            self.session,
            self.UserService.delete_user,
            user_id,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{user_id}")
async def get(
    user_id: int,
    ctrl: UserIdController = Depends(UserIdController),
) -> dict[str, Any]:
    return await ctrl.get(user_id)


@router.patch("/{user_id}")
async def update(
    user_id: int,
    body: UpdateUserRequest,
    ctrl: UserIdController = Depends(UserIdController),
) -> dict[str, Any]:
    return await ctrl.update(user_id, body)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    user_id: int,
    ctrl: UserIdController = Depends(UserIdController),
) -> Response:
    return await ctrl.delete(user_id)
