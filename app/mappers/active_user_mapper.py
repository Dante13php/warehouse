from __future__ import annotations

import logging

from app.data.auth_user import AuthUser
from app.data.token import TokenData
from app.errors.auth.unauthenticated_error import UnauthenticatedError
from app.infrastructure.ioc import Ioc
from app.mappers.abstract_mapper import AbstractMapper

logger = logging.getLogger(__name__)

# Role claim literals issued by create_access_token in app/helpers/jwt.py.
# These must stay in sync with token issuance.
# TODO: replace with a Role enum once the role vocabulary is codified.
_ROLE_ADMIN = "admin"
_ROLE_MANAGER = "manager"


class ActiveUserMapper(AbstractMapper):
    def __init__(self, ioc: Ioc) -> None:
        super().__init__(ioc)
        self._user: AuthUser | None = None
        self._api_key: str | None = None

    def is_initialized(self) -> bool:
        return self._ioc.claims is not None

    def _require_claims(self) -> TokenData:
        claims = self._ioc.claims
        if claims is None:
            raise UnauthenticatedError(
                "The active user is not initialized: this request is not authenticated."
            )
        return claims

    @property
    def user_id(self) -> str:
        return self._require_claims().sub

    @property
    def tenant_id(self) -> str:
        return self._require_claims().tenant_id

    @property
    def role(self) -> str:
        return self._require_claims().role

    def is_admin(self) -> bool:
        return self.is_initialized() and self._ioc.claims.role == _ROLE_ADMIN  # type: ignore[union-attr]

    def is_manager(self) -> bool:
        return self.is_initialized() and self._ioc.claims.role == _ROLE_MANAGER  # type: ignore[union-attr]

    async def load(self) -> AuthUser:
        self._require_claims()
        if self._user is None:
            self._user = await self._ioc.UserStorage.get_by_id(self.user_id)
        return self._user

    @property
    def user(self) -> AuthUser:
        # A property cannot await the async DB load, so load() must run first.
        self._require_claims()
        if self._user is None:
            raise UnauthenticatedError(
                "The full user record has not been loaded yet; "
                "call 'await ActiveUserMapper.load()' before reading profile fields."
            )
        return self._user

    @property
    def email(self) -> str:
        return self.user.email

    async def get_api_key(self) -> str | None:
        self._require_claims()
        if self._api_key is None:
            self._api_key = await self._ioc.ApiKeyStorage.get_api_key_by_user_id(
                self.user_id
            )
        return self._api_key
