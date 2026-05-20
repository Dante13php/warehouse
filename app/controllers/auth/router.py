import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.controllers.base_controller import BaseController
from app.requests.auth.login_request import LoginRequest
from app.requests.auth.logout_request import LogoutRequest
from app.requests.auth.refresh_request import RefreshRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class AuthController(BaseController):
    async def login(self, body: LoginRequest) -> dict:
        try:
            return await self.AuthService.login(
                email=body.email,
                password=body.password,
            )
        except self.InvalidCredentialsError.target:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

    async def refresh(self, body: RefreshRequest) -> dict:
        try:
            return await self.AuthService.refresh(
                refresh_token=body.refresh_token,
            )
        except self.InvalidTokenError.target:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
                headers={"WWW-Authenticate": "Bearer"},
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
