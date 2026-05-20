import logging

from fastapi import APIRouter, Depends, Response, status

from app.controllers.base_controller import BaseController
from app.requests.auth.login_request import LoginRequest
from app.requests.auth.logout_request import LogoutRequest
from app.requests.auth.refresh_request import RefreshRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthController(BaseController):
    # CloudSale flat-flow controller: no try/except. Domain errors raised by the
    # service (subclasses of ApplicationError) bubble up to the global
    # ApplicationError handler in app/main.py, which maps them to the right HTTP
    # status/detail. The controller only routes input to the service and shapes
    # the response.
    #
    # NOTE on TransactionHelper: the CloudSale pattern wraps every mutation in
    # TransactionHelper.wrap(session, ...). The auth operations here are
    # Redis-only (RefreshTokenStorage) and run on requests that carry NO SQL
    # AsyncSession (get_ioc binds session=None), so self.session is unavailable
    # and self.transaction.wrap(self.session, ...) cannot run. The transaction
    # boundary is therefore intentionally omitted until auth gains SQL-backed
    # writes; the flat-flow / no-try-except half of the pattern is applied now.

    async def login(self, body: LoginRequest) -> dict:
        return await self.AuthService.login(
            email=body.email,
            password=body.password,
        )

    async def refresh(self, body: RefreshRequest) -> dict:
        return await self.AuthService.refresh(
            refresh_token=body.refresh_token,
        )

    async def logout(self, body: LogoutRequest) -> Response:
        await self.AuthService.logout(refresh_token=body.refresh_token)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/login")
async def login(
    body: LoginRequest,
    ctrl: AuthController = Depends(AuthController),
) -> dict:
    return await ctrl.login(body)


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    ctrl: AuthController = Depends(AuthController),
) -> dict:
    return await ctrl.refresh(body)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    ctrl: AuthController = Depends(AuthController),
) -> Response:
    return await ctrl.logout(body)
