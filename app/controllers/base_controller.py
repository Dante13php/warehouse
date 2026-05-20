from __future__ import annotations

from typing import Any

from fastapi import Depends

from app.infrastructure.ioc import Ioc, get_ioc


class BaseController:
    def __init__(self, ioc: Ioc = Depends(get_ioc)) -> None:
        self._ioc = ioc

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
