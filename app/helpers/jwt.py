import logging
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.data.token import TokenData
from app.infrastructure.settings import Settings

logger = logging.getLogger(__name__)


def create_access_token(sub: str, tenant_id: str, role: str, settings: Settings) -> str:
    """Create a signed JWT access token with sub, tenant_id, role, and exp claims."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    to_encode = {"sub": sub, "tenant_id": tenant_id, "role": role, "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> TokenData:
    """Decode and validate a JWT access token. Raises JWTError on failure."""
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )

    if "sub" not in payload or "tenant_id" not in payload or "role" not in payload:
        raise JWTError("Missing required claims in token")

    return TokenData.from_claims(payload)
