import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.data.token import TokenData
from app.helpers.jwt import decode_access_token
from app.infrastructure.settings import Settings, get_settings

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    settings: Settings = Depends(get_settings),
) -> TokenData:
    try:
        return decode_access_token(token, settings)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_authentication(request: Request) -> TokenData:
    """Authentication gate for protected routes.

    Reads the identity that ``AuthMiddleware`` established on
    ``request.state.token_data`` (the single source of identity for both the JWT
    and API-key channels) and returns 401 when the request is anonymous. It does
    NOT decode a token itself or re-resolve a credential — that already happened
    in the middleware.

    This is the auth-only gate (plan Q7: no role-based authorization in this
    task). Apply it as a route dependency on every protected endpoint.
    """
    token_data: TokenData | None = getattr(request.state, "token_data", None)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token_data
