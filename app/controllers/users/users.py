from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, status

from app.controllers.db_base_controller import DbBaseController
from app.helpers.security import require_authentication
from app.requests.users.create_user_request import CreateUserRequest

logger = logging.getLogger(__name__)

# Collection-level routes only (GET /users, POST /users). Single-resource routes
# (those keyed by the {user_id} path parameter) live in the user_id/ subfolder,
# per the path-parameter-subfolder convention. Every route requires
# authentication; the gate reads middleware-established identity and 401s when
# anonymous.
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

    async def get(self) -> list[dict[str, Any]]:
        users = await self.UserService.list_users()
        return [user.to_response() for user in users]

    async def create(self, body: CreateUserRequest) -> dict[str, Any]:
        user = await self.transaction.wrap(
            self.session,
            self.UserService.create_user,
            email=body.email,
            password=body.password,
            role=body.role,
        )
        return user.to_response()


@router.get("")
async def get(
    ctrl: UsersController = Depends(UsersController),
) -> list[dict[str, Any]]:
    return await ctrl.get()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(
    body: CreateUserRequest,
    ctrl: UsersController = Depends(UsersController),
) -> dict[str, Any]:
    return await ctrl.create(body)
