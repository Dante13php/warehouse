from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.token import TokenData
from app.infrastructure.database import get_session
from app.infrastructure.ioc import Ioc
from app.infrastructure.redis import get_redis
from app.infrastructure.settings import Settings, get_settings

logger = logging.getLogger(__name__)


async def get_ioc_with_session(
    request: Request,
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> AsyncGenerator[Ioc, None]:
    """IoC dependency for DB-backed routes (plan Q2).

    Opens a per-request ``AsyncSession`` and binds it onto the ``Ioc`` so
    ``UserStorage`` can query and the controller can wrap mutations via
    ``self.transaction.wrap(self.session, ...)``. The session targets the
    configured per-tenant template DB until email->tenant routing lands
    (plan Q8); the engine already uses NullPool + disabled prepared-statement
    cache, which is PgBouncer-safe (see app/infrastructure/database.py).

    Identity still comes solely from AuthMiddleware (request.state.token_data);
    this dependency never decodes a token. The session is always closed after
    the request, whether or not the handler raised.
    """
    token_data: TokenData | None = getattr(request.state, "token_data", None)
    # Interim DB target (plan Q8): per-tenant template DB. Replaced by
    # registry-driven email->tenant routing in the follow-up task.
    db_name = settings.alembic_template_db
    session_factory = get_session(db_name)
    session: AsyncSession = session_factory()
    try:
        yield Ioc(
            session=session,
            token_data=token_data,
            redis=redis,
            settings=settings,
        )
    finally:
        await session.close()
