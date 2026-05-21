from __future__ import annotations

from typing import Any

from fastapi import Depends

from app.infrastructure.db_session import get_ioc_with_session
from app.infrastructure.ioc import Ioc


class DbBaseController:
    """Base controller for DB-backed endpoints.

    Identical surface to ``BaseController`` (``self.<ClassName>`` proxies to the
    IoC), but bootstraps from ``get_ioc_with_session`` so the request carries a
    real ``AsyncSession`` (plan Q2). DB-backed controllers extend this; pure
    Redis/no-DB controllers (e.g. /auth) extend ``BaseController``.

    This base — not the concrete controllers — owns the ``__init__``, so concrete
    controllers still never declare one (RULES).
    """

    def __init__(self, ioc: Ioc = Depends(get_ioc_with_session)) -> None:
        self._ioc = ioc

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._ioc, name)
