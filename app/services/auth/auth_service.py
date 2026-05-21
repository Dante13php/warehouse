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
        settings = self.settings
        # Interim tenant DB (plan Q8): users live in a per-tenant DB; full
        # email->tenant registry routing is a named follow-up. Until then the
        # lookup runs against the configured template/tenant DB the request
        # session is bound to. Passed for signature compatibility.
        db_name = settings.alembic_template_db
        user_lookup = self.UserLookupService
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
        refresh_storage = self.RefreshTokenStorage
        await refresh_storage.delete(refresh_token)
