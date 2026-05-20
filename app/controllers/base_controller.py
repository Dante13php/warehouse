from __future__ import annotations

from typing import Any

from fastapi import Depends

from app.infrastructure.ioc import Ioc, get_ioc


class BaseController:
    """Base class for all controllers.

    Owns the single ``Depends(get_ioc)`` injection point so individual routes
    never name the container. Concrete controllers subclass this and access
    collaborators and request-scoped resources through ``self.X`` (e.g.
    ``self.AuthService``, ``self.InvalidCredentialsError``), which delegates to
    the per-request :class:`Ioc` via ``__getattr__``.
    """

    def __init__(self, ioc: Ioc = Depends(get_ioc)) -> None:
        self._ioc = ioc

    def __getattr__(self, name: str) -> Any:
        # Leading-underscore names (``_ioc`` before __init__ runs, dunders from
        # framework/copy introspection) must not trigger IoC resolution, and the
        # guard prevents infinite recursion before ``_ioc`` is assigned.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
