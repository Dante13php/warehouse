from __future__ import annotations

import logging
import secrets

from app.helpers.jwt import create_access_token
from app.helpers.password import verify_password
from app.services.abstract_service import AbstractService

logger = logging.getLogger(__name__)

_DUMMY_HASH = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"


class AuthService(AbstractService):
    async def login(self, email: str, password: str) -> dict:
        """
        Verify credentials and return access + refresh tokens.
        Always runs bcrypt for unknown users to prevent timing-based enumeration.
        """
        settings = self.settings
        db_name = settings.alembic_shared_db
        user_lookup = self.NotImplementedUserLookupService
        refresh_storage = self.RefreshTokenStorage

        user = await user_lookup.get_by_email(email, db_name)

        if user is None:
            # Timing-safe: run a dummy verify so the response time is consistent
            verify_password(password, _DUMMY_HASH)
            raise self.InvalidCredentialsError.get("Invalid credentials")

        if not verify_password(password, user.password_hash):
            raise self.InvalidCredentialsError.get("Invalid credentials")

        access_token = create_access_token(
            sub=user.id,
            tenant_id=user.tenant_id,
            role=user.role,
            settings=settings,
        )
        refresh_token = secrets.token_urlsafe(32)

        await refresh_storage.save(
            sub=user.id,
            tenant_id=user.tenant_id,
            role=user.role,
            token=refresh_token,
            ttl_days=settings.refresh_token_expire_days,
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "refresh_token": refresh_token,
        }

    async def refresh(self, refresh_token: str) -> dict:
        """
        Validate the refresh token in Redis, rotate it, and return a new access token.
        Raises InvalidTokenError if the token is not found or already revoked.
        """
        settings = self.settings
        refresh_storage = self.RefreshTokenStorage

        claims = await refresh_storage.get_and_delete_claims(refresh_token)
        if claims is None:
            raise self.InvalidTokenError.get(
                "Refresh token is invalid or has expired"
            )

        sub: str = claims["sub"]
        tenant_id: str = claims["tenant_id"]
        role: str = claims["role"]

        new_refresh_token = secrets.token_urlsafe(32)
        await refresh_storage.save(
            sub=sub,
            tenant_id=tenant_id,
            role=role,
            token=new_refresh_token,
            ttl_days=settings.refresh_token_expire_days,
        )

        access_token = create_access_token(
            sub=sub,
            tenant_id=tenant_id,
            role=role,
            settings=settings,
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "refresh_token": new_refresh_token,
        }

    async def logout(self, refresh_token: str) -> None:
        """Revoke the refresh token. Idempotent — no error if already absent."""
        refresh_storage = self.RefreshTokenStorage
        await refresh_storage.delete(refresh_token)
