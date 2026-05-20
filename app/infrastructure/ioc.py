
from __future__ import annotations

import importlib
import logging
import pkgutil
import re
from typing import TYPE_CHECKING, Any

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.data.token import TokenData
from app.infrastructure.redis import get_redis
from app.infrastructure.settings import Settings, get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_SUFFIX_TO_PACKAGE: dict[str, str] = {
    "Service": "app.services",
    "Storage": "app.storages",
    "Mapper": "app.mappers",
    "Request": "app.requests",
    "Error": "app.errors",
}

# Suffixes whose classes are instantiated and memoized as request-scoped
# collaborators. Others are returned as factories.
_INSTANTIATED_SUFFIXES: frozenset[str] = frozenset({"Service", "Storage", "Mapper"})

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")

# Process-level cache: class name -> resolved class object. Safe to cache
# because module/class objects are immutable for the process lifetime. This is
# NOT request state — only the resolved *type*, never an instance.
_CLASS_CACHE: dict[str, type] = {}


def _camel_to_snake(name: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", name).lower()


class IocResolutionError(AttributeError):
    # Subclasses AttributeError so hasattr/getattr-with-default still work correctly.
    pass


class GenericFactory:
    def __init__(self, target: type) -> None:
        self._target = target

    @property
    def target(self) -> type:
        return self._target

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self._target(*args, **kwargs)


class ErrorFactory(GenericFactory):
    pass


class Ioc:

    def __init__(
        self,
        session: AsyncSession | None,
        token_data: TokenData | None,
        redis: Redis,
        settings: Settings,
    ) -> None:
        # Leading underscore so these never collide with __getattr__ resolution
        # (Python only calls __getattr__ for *missing* attributes).
        self._session = session
        self._token_data = token_data
        self._redis = redis
        self._settings = settings
        # Request-scoped instance cache: class name -> live instance.
        self._instances: dict[str, Any] = {}

    # ----- request-scoped resources -------------------------------------

    @property
    def session(self) -> AsyncSession:
        if self._session is None:
            raise IocResolutionError(
                "This request has no database session bound to the container."
            )
        return self._session

    @property
    def claims(self) -> TokenData | None:
        # Name intentionally does NOT end with a known IoC suffix to avoid shadowing __getattr__ resolution.
        return self._token_data

    @property
    def tenant_id(self) -> str | None:
        if self._token_data is not None:
            return self._token_data.tenant_id
        return None

    @property
    def redis(self) -> Redis:
        return self._redis

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def transaction(self) -> Any:
        cache_key = "TransactionHelper"
        existing = self._instances.get(cache_key)
        if existing is not None:
            return existing
        from app.infrastructure.transaction import TransactionHelper

        helper = TransactionHelper()
        self._instances[cache_key] = helper
        return helper

    # ----- dynamic resolution -------------------------------------------

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)

        suffix = self._match_suffix(name)
        if suffix is None:
            raise IocResolutionError(
                f"Cannot resolve '{name}': name does not end with a known IoC "
                f"suffix {sorted(_SUFFIX_TO_PACKAGE)}."
            )

        if suffix in _INSTANTIATED_SUFFIXES:
            return self._resolve_instance(name)

        target = self._load_class(name, suffix)
        if suffix == "Error":
            return ErrorFactory(target)
        return GenericFactory(target)

    def _match_suffix(self, name: str) -> str | None:
        for suffix in _SUFFIX_TO_PACKAGE:
            if name.endswith(suffix) and len(name) > len(suffix):
                return suffix
        return None

    def _resolve_instance(self, name: str) -> Any:
        existing = self._instances.get(name)
        if existing is not None:
            return existing
        suffix = self._match_suffix(name)
        assert suffix is not None  # guaranteed by caller
        target = self._load_class(name, suffix)
        instance = target(self)
        self._instances[name] = instance
        return instance

    def _load_class(self, name: str, suffix: str) -> type:
        cached = _CLASS_CACHE.get(name)
        if cached is not None:
            return cached

        package_root = _SUFFIX_TO_PACKAGE[suffix]
        module_stem = _camel_to_snake(name)
        target = self._find_class_in_package(package_root, module_stem, name)
        if target is None:
            raise IocResolutionError(
                f"Cannot resolve '{name}': no module '{module_stem}.py' exporting "
                f"class '{name}' found under package '{package_root}'."
            )
        _CLASS_CACHE[name] = target
        return target

    @staticmethod
    def _find_class_in_package(
        package_root: str, module_stem: str, class_name: str
    ) -> type | None:
        package = importlib.import_module(package_root)
        for module_info in pkgutil.walk_packages(
            package.__path__, prefix=f"{package_root}."
        ):
            if module_info.ispkg:
                continue
            if module_info.name.rsplit(".", 1)[-1] != module_stem:
                continue
            module = importlib.import_module(module_info.name)
            candidate = getattr(module, class_name, None)
            if isinstance(candidate, type):
                return candidate
        return None


async def get_ioc(
    request: Request,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> Ioc:
    # Identity is established once per request by ``AuthMiddleware``, which runs
    # before any route handler and attaches the verified ``TokenData`` to
    # ``request.state.token_data``. ``get_ioc`` never decodes a token itself —
    # the middleware is the single source of identity. If the middleware has not
    # run (e.g. a bare test harness), default to anonymous; no silent re-decode.
    token_data: TokenData | None = getattr(request.state, "token_data", None)
    return Ioc(session=None, token_data=token_data, redis=redis, settings=settings)
