from __future__ import annotations

import json
import logging

from app.storages.abstract_storage import AbstractStorage

logger = logging.getLogger(__name__)

_KEY_PREFIX = "refresh:"


class RefreshTokenStorage(AbstractStorage):
    async def save(
        self,
        sub: str,
        tenant_id: str,
        role: str,
        token: str,
        ttl_days: int,
    ) -> None:
        """Store full claims for a refresh token keyed by the token value with a TTL in days."""
        ttl_seconds = ttl_days * 86400
        key = f"{_KEY_PREFIX}{token}"
        payload = json.dumps({"sub": sub, "tenant_id": tenant_id, "role": role})
        await self.redis.set(key, payload, ex=ttl_seconds)

    async def get_claims(self, token: str) -> dict | None:
        """Return the claims dict associated with the refresh token, or None if not found."""
        key = f"{_KEY_PREFIX}{token}"
        value: str | None = await self.redis.get(key)
        if value is None:
            return None
        return json.loads(value)

    async def get_and_delete_claims(self, token: str) -> dict | None:
        """Atomically read and delete the refresh token entry. Returns claims or None if not found."""
        key = f"{_KEY_PREFIX}{token}"
        value: str | None = await self.redis.getdel(key)
        if value is None:
            return None
        return json.loads(value)

    async def delete(self, token: str) -> None:
        """Delete the refresh token entry. Idempotent — no error if already absent."""
        key = f"{_KEY_PREFIX}{token}"
        await self.redis.delete(key)
