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


class CurrentUserMapper(AbstractMapper):
    """Per-request holder of the active user, mirroring CloudSale's
    ``ActiveUserMapper``.

    Identity (``user_id`` / ``tenant_id`` / ``role``) is established once per
    request by ``AuthMiddleware`` from verified credentials (JWT bearer or API
    key) and surfaced here through ``self._ioc.claims``. The auth *mechanism* is
    abstracted away — this mapper only ever sees a verified user.

    Beyond the lightweight claim-backed identity, the mapper holds the **full
    user record** (:class:`AuthUser`). Because the load is an async DB call (and
    Python properties cannot ``await``), the record is fetched and memoized by
    ``await load()``; profile-only accessors (e.g. :attr:`email`) then read from
    the memoized record. This is the Python equivalent of ``ActiveUserMapper``
    holding ``$userData`` and lazy-loading on first use. Claim-backed properties
    never trigger a DB hit.
    """

    def __init__(self, ioc: Ioc) -> None:
        super().__init__(ioc)
        # Memoized per-request full record / API key, lazy-loaded on first use.
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

    # ----- claim-backed identity (no DB access) -------------------------

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

    # ----- full user record (lazy-loaded, memoized) ---------------------

    async def load(self) -> AuthUser:
        """Lazy-load and memoize the full user record (async).

        Mirrors ``ActiveUserMapper`` holding the DB-loaded ``$userData``. Loads
        via ``UserStorage`` keyed by the verified ``user_id`` and is safe to call
        repeatedly — the record is fetched at most once per request.
        """
        self._require_claims()
        if self._user is None:
            self._user = await self._ioc.UserStorage.get_by_id(self.user_id)
        return self._user

    @property
    def user(self) -> AuthUser:
        """The memoized full user record.

        Requires :meth:`load` to have run for this request (a property cannot
        ``await`` the async DB load). Raises if read before loading.
        """
        self._require_claims()
        if self._user is None:
            raise UnauthenticatedError(
                "The full user record has not been loaded yet; "
                "call 'await CurrentUserMapper.load()' before reading profile fields."
            )
        return self._user

    @property
    def email(self) -> str:
        # Profile-only field: served from the memoized full record.
        return self.user.email

    async def get_api_key(self) -> str | None:
        """Lazy-load the user's API key from storage (mirrors PHP getApiKey()).

        Fetched at most once per request and memoized on the instance.
        """
        self._require_claims()
        if self._api_key is None:
            self._api_key = await self._ioc.ApiKeyStorage.get_api_key_by_user_id(
                self.user_id
            )
        return self._api_key
