from __future__ import annotations

from typing import Any

from app.infrastructure.ioc import Ioc


class AbstractStorage:
    def __init__(self, ioc: Ioc) -> None:
        self._ioc = ioc

    def __getattr__(self, name: str) -> Any:
        # Leading-underscore names must skip IoC resolution; this also prevents
        # infinite recursion before _ioc is assigned during __init__.
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
