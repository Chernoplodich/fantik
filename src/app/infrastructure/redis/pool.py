"""Фабрики Redis connection pool'ов — отдельно для кэша, FSM и TaskIQ."""

from __future__ import annotations

from redis.asyncio import ConnectionPool

from app.core.config import Settings


def build_redis_cache_pool(settings: Settings) -> ConnectionPool:
    return ConnectionPool.from_url(
        settings.redis_url_for(settings.redis_cache_db),
        max_connections=50,
        decode_responses=False,  # bytes — совместимо с msgpack
    )


def build_redis_fsm_pool(settings: Settings) -> ConnectionPool:
    return ConnectionPool.from_url(
        settings.redis_url_for(settings.redis_fsm_db),
        max_connections=50,
        decode_responses=False,
    )
