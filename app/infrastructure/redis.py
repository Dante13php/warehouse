from collections.abc import AsyncGenerator

from redis.asyncio import ConnectionPool, Redis

from app.infrastructure.settings import get_settings

_pool: ConnectionPool | None = None


def get_redis_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password,
            decode_responses=True,
        )
    return _pool


async def get_redis() -> AsyncGenerator[Redis, None]:
    client = Redis(connection_pool=get_redis_pool())
    try:
        yield client
    finally:
        await client.aclose()
