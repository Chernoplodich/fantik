"""RedisSearchCache: msgpack TTL-кэш для инлайн-поиска и suggest.

Универсальный: хранит произвольные JSON-совместимые структуры
(`list[dict]` — карточки инлайн-результатов, `list[str]` — подсказки).
"""

from __future__ import annotations

import msgpack
from redis.asyncio import Redis

from app.application.search.ports import ISearchCache


class RedisSearchCache(ISearchCache):
    def __init__(self, redis: Redis) -> None:
        self._r = redis

    async def get(self, key: str) -> object | None:
        raw = await self._r.get(key)
        if raw is None:
            return None
        try:
            return msgpack.unpackb(raw, raw=False)
        except (msgpack.UnpackException, ValueError):
            return None

    async def setex(self, key: str, ttl_s: int, value: object) -> None:
        payload = msgpack.packb(value, use_bin_type=True)
        await self._r.setex(key, ttl_s, payload)
