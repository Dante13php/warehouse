from __future__ import annotations

from typing import Any

from app.infrastructure.ioc import Ioc


class AbstractMapper:
    def __init__(self, ioc: Ioc) -> None:
        self._ioc = ioc

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
