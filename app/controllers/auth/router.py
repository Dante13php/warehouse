import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.infrastructure.ioc import Ioc, get_ioc
from app.requests.auth.login_request import LoginRequest
from app.requests.auth.logout_request import LogoutRequest
from app.requests.auth.refresh_request import RefreshRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    body: LoginRequest,
    ioc: Ioc = Depends(get_ioc),
) -> dict:
    try:
        return await ioc.AuthService.login(
            email=body.email,
            password=body.password,
        )
    except ioc.InvalidCredentialsError.target:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh")
async def refresh(
    body: RefreshRequest,
    ioc: Ioc = Depends(get_ioc),
) -> dict:
    try:
        return await ioc.AuthService.refresh(
            refresh_token=body.refresh_token,
        )
    except ioc.InvalidTokenError.target:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    ioc: Ioc = Depends(get_ioc),
) -> Response:
    await ioc.AuthService.logout(refresh_token=body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
