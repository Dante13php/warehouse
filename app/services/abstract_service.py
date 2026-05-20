from __future__ import annotations

from typing import Any

from app.infrastructure.ioc import Ioc


class AbstractService:
    """Base class for all services.

    Concrete services subclass this and access collaborators and request-scoped
    resources through ``self.X`` (e.g. ``self.UserStorage``, ``self.redis``,
    ``self.settings``), which delegates to the per-request :class:`Ioc` via
    ``__getattr__``. The container is constructor-injected by the IoC resolver
    and never named in business code.
    """

    def __init__(self, ioc: Ioc) -> None:
        self._ioc = ioc

    def __getattr__(self, name: str) -> Any:
        # Leading-underscore names (``_ioc`` before __init__ runs, dunders from
        # introspection) must not trigger IoC resolution, and the guard prevents
        # infinite recursion before ``_ioc`` is assigned.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
