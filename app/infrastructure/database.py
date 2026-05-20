from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.infrastructure.settings import get_settings

_engine_cache: dict[str, AsyncEngine] = {}


def _build_url(db_name: str) -> str:
    settings = get_settings()
    return (
        f"postgresql+asyncpg://{settings.app_postgres_user}:"
        f"{settings.app_postgres_password}@{settings.app_postgres_host}:"
        f"{settings.app_postgres_port}/{db_name}"
    )


def get_engine(db_name: str) -> AsyncEngine:
    engine = _engine_cache.get(db_name)
    if engine is None:
        engine = create_async_engine(
            _build_url(db_name),
            poolclass=NullPool,
            connect_args={"prepared_statement_cache_size": 0},
        )
        _engine_cache[db_name] = engine
    return engine


def get_session(db_name: str) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(db_name),
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_db(db_name: str) -> AsyncGenerator[AsyncSession, None]:
    session_factory = get_session(db_name)
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
