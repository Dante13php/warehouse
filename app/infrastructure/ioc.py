"""Per-request Inversion-of-Control container.

The container is the official dependency-injection mechanism of the Warehouse
backend. A new :class:`Ioc` instance is created for every HTTP request and
carries that request's :class:`AsyncSession`, ``tenant_id``, Redis client and
:class:`Settings`. It resolves classes dynamically by *class name* using a
suffix → layer convention and ``importlib`` module loading.

Resolution is Strategy B (convention-strict): every resolvable class lives in a
module whose file name is the snake_case of the class name (PHP-identical path
derivation). The resolver scans the layer package recursively so domain nesting
(``services/auth/auth_service.py``) does not need to be encoded in the class
name.

Suffix → layer rules:

==================  =========  =================================  ==========
Requested suffix    Layer      Package root                       Returns
==================  =========  =================================  ==========
``*Service``        service    ``app.services``                   instance
``*Storage``        storage    ``app.storages``                   instance
``*Request``        request    ``app.requests``                   factory
``*Error``          error      ``app.errors``                     factory
==================  =========  =================================  ==========

``*Service`` / ``*Storage`` are instantiated and memoized per request.
``*Request`` / ``*Error`` are not container-owned values: the container returns
a thin factory (``GenericFactory`` / ``ErrorFactory``) whose ``.get(...)``
constructs the instance, mirroring the CloudSale PHP factory ergonomics.

The resolution name is always a literal attribute access in source code
(``ioc.AuthService``); it is never derived from request data, so the dynamic
``importlib`` lookup cannot be driven by user input.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import re
from typing import TYPE_CHECKING, Any

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from redis.asyncio import Redis

from app.helpers.jwt import decode_access_token
from app.infrastructure.redis import get_redis
from app.infrastructure.settings import Settings, get_settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_SUFFIX_TO_PACKAGE: dict[str, str] = {
    "Service": "app.services",
    "Storage": "app.storages",
    "Request": "app.requests",
    "Error": "app.errors",
}

# Suffixes whose classes are instantiated and memoized as request-scoped
# collaborators. Others are returned as factories.
_INSTANTIATED_SUFFIXES: frozenset[str] = frozenset({"Service", "Storage"})

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")

# Process-level cache: class name -> resolved class object. Safe to cache
# because module/class objects are immutable for the process lifetime. This is
# NOT request state — only the resolved *type*, never an instance.
_CLASS_CACHE: dict[str, type] = {}


def _camel_to_snake(name: str) -> str:
    """Convert a PascalCase class name to a snake_case module file stem."""
    return _CAMEL_BOUNDARY.sub("_", name).lower()


class IocResolutionError(AttributeError):
    """Raised when the container cannot resolve a requested class name.

    Subclasses :class:`AttributeError` so that normal attribute-protocol
    consumers (``hasattr``, ``getattr`` with default) still behave correctly.
    """


class GenericFactory:
    """Factory wrapper for non-instantiated classes (e.g. ``*Request``).

    Mirrors the CloudSale PHP factory: ``ioc.LoginRequest`` yields a factory and
    ``ioc.LoginRequest.get(data)`` constructs the instance.
    """

    def __init__(self, target: type) -> None:
        self._target = target

    @property
    def target(self) -> type:
        """The wrapped class object."""
        return self._target

    def get(self, *args: Any, **kwargs: Any) -> Any:
        """Construct and return an instance of the wrapped class."""
        return self._target(*args, **kwargs)


class ErrorFactory(GenericFactory):
    """Factory wrapper for ``*Error`` classes.

    ``ioc.InvalidCredentialsError`` yields an :class:`ErrorFactory`;
    ``ioc.InvalidCredentialsError.get("msg")`` raises-ready constructs the error.
    """


class Ioc:
    """Per-request dependency container.

    Construct one per request via :func:`get_ioc`. Holds the request-scoped
    ``session``, ``tenant_id``, ``redis`` and ``settings``. Resolves
    collaborators lazily by class name via ``__getattr__``.
    """

    def __init__(
        self,
        session: AsyncSession | None,
        tenant_id: str | None,
        redis: Redis,
        settings: Settings,
    ) -> None:
        # Leading underscore so these never collide with __getattr__ resolution
        # (Python only calls __getattr__ for *missing* attributes).
        self._session = session
        self._tenant_id = tenant_id
        self._redis = redis
        self._settings = settings
        # Request-scoped instance cache: class name -> live instance.
        self._instances: dict[str, Any] = {}

    # ----- request-scoped resources -------------------------------------

    @property
    def session(self) -> AsyncSession:
        """The request's AsyncSession. Raises if the request has no DB scope."""
        if self._session is None:
            raise IocResolutionError(
                "This request has no database session bound to the container."
            )
        return self._session

    @property
    def tenant_id(self) -> str | None:
        """Tenant id sourced from verified JWT claims; ``None`` for public routes."""
        return self._tenant_id

    @property
    def redis(self) -> Redis:
        """The request's Redis client."""
        return self._redis

    @property
    def settings(self) -> Settings:
        """Application settings."""
        return self._settings

    @property
    def transaction(self) -> Any:
        """Resolve the request-scoped :class:`TransactionHelper`.

        Exposed via the container so controllers touch only ``ioc`` when wrapping
        mutations: ``await ioc.transaction.wrap(ioc.session, fn, ...)``.
        """
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
        """Resolve a class by its name suffix.

        ``*Service`` / ``*Storage`` -> memoized request-scoped instance.
        ``*Request`` -> :class:`GenericFactory`.
        ``*Error`` -> :class:`ErrorFactory`.
        Unknown suffixes raise :class:`IocResolutionError`.
        """
        # Names that aren't resolvable class requests (dunders, private) must not
        # trigger importlib scanning.
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
        """Recursively scan ``package_root`` for ``<module_stem>.py`` exporting ``class_name``.

        The module file name is fully derived from the class name (Strategy B),
        so this scan only walks packages — it never interprets request data.
        """
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


# Optional bearer scheme: auth routes are public, so a token may be absent.
# auto_error=False means a missing token yields ``None`` instead of a 401.
_optional_bearer = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


async def get_ioc(
    token: str | None = Depends(_optional_bearer),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> Ioc:
    """FastAPI dependency that builds the per-request :class:`Ioc`.

    This is the only ``Depends`` controllers use to obtain dependencies. It is
    request-scoped: a fresh container is created per request and is never cached
    at module level.

    ``tenant_id`` is resolved exclusively from verified JWT claims when a valid
    bearer token is present. It is never read from the request body or query
    params. Public routes (no token) get ``tenant_id=None``.
    """
    tenant_id: str | None = None
    if token is not None:
        try:
            claims = decode_access_token(token, settings)
            tenant_id = claims.tenant_id
        except JWTError:
            # Invalid token on a route that does not require auth: treat as
            # anonymous rather than failing. Routes that require auth enforce
            # validation via their own dependency (get_current_user).
            tenant_id = None
    return Ioc(session=None, tenant_id=tenant_id, redis=redis, settings=settings)
